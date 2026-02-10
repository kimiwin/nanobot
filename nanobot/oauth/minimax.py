"""
MiniMax OAuth for nanobot
参考 OpenClaw: openclaw/extensions/minimax-portal-auth/oauth.ts
"""

import os
import json
import time
import asyncio
import hashlib
from typing import Optional

import httpx

MINIMAX_OAUTH_CONFIG = {
    "cn": {
        "baseUrl": "https://api.minimaxi.com",
        "clientId": "78257093-7e40-4613-99e0-527b14b39113",
    },
    "global": {
        "baseUrl": "https://api.minimax.io",
        "clientId": "78257093-7e40-4613-99e0-527b14b39113",
    },
}

MINIMAX_OAUTH_SCOPE = "group_id profile model.completion"
MINIMAX_OAUTH_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:user_code"
TOKEN_FILE = os.path.expanduser("~/.nanobot/.minimax_token")


def generate_pkce():
    verifier = os.urandom(32).hex()
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    state = os.urandom(16).hex()
    return verifier, challenge, state


def to_form_urlencoded(data: dict) -> str:
    return "&".join(f"{k}={v}" for k, v in data.items())


async def request_oauth_code(region: str = "cn"):
    config = MINIMAX_OAUTH_CONFIG[region]
    verifier, challenge, state = generate_pkce()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config['baseUrl']}/oauth/code",
            data=to_form_urlencoded({
                "response_type": "code",
                "client_id": config["clientId"],
                "scope": MINIMAX_OAUTH_SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if not response.ok:
            raise Exception(f"OAuth code request failed: {response.text}")
        return response.json()


async def poll_oauth_token(user_code: str, verifier: str, region: str = "cn") -> dict:
    config = MINIMAX_OAUTH_CONFIG[region]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config['baseUrl']}/oauth/token",
            data=to_form_urlencoded({
                "grant_type": MINIMAX_OAUTH_GRANT_TYPE,
                "client_id": config["clientId"],
                "user_code": user_code,
                "code_verifier": verifier,
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        return response.json()


async def login_minimax(region: str = "cn"):
    """Complete MiniMax OAuth login flow."""
    print(f"Starting MiniMax OAuth ({region})...")
    oauth = await request_oauth_code(region)
    print(f"\nPlease visit: {oauth['verification_uri']}")
    print(f"Enter code: {oauth['user_code']}")
    
    verifier = generate_pkce()[0]
    expire_time = time.time() + oauth.get("expires_in", 300)
    poll_interval = oauth.get("interval", 2)
    
    while time.time() < expire_time:
        await asyncio.sleep(poll_interval)
        result = await poll_oauth_token(oauth["user_code"], verifier, region)
        
        if result.get("status") == "success":
            print("\n✅ OAuth login successful!")
            return {
                "access": result["access_token"],
                "refresh": result["refresh_token"],
                "expires": result["expired_in"],
                "region": region,
            }
        elif result.get("status") == "error":
            raise Exception(f"OAuth failed: {result.get('message')}")
        poll_interval = min(poll_interval * 1.5, 10)
    
    raise Exception("OAuth timeout")


async def refresh_access_token(refresh_token: str, region: str = "cn") -> dict:
    config = MINIMAX_OAUTH_CONFIG[region]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config['baseUrl']}/oauth/token",
            data=to_form_urlencoded({
                "grant_type": "refresh_token",
                "client_id": config["clientId"],
                "refresh_token": refresh_token,
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if not response.ok:
            raise Exception(f"Token refresh failed: {response.text}")
        return response.json()


class MiniMaxOAuthToken:
    def __init__(self, access: str, refresh: str, expires: int):
        self.access = access
        self.refresh = refresh
        self.expires = expires
        self.expires_at = time.time() + expires
    
    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - 60)


async def get_minimax_access_token(force_refresh: bool = False) -> str:
    """Get valid access token."""
    if os.path.exists(TOKEN_FILE) and not force_refresh:
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        token = MiniMaxOAuthToken(token_data["access"], token_data["refresh"], token_data["expires"])
        if not token.is_expired():
            return token.access
        try:
            result = await refresh_access_token(token.refresh, token_data.get("region", "cn"))
            token_data["access"] = result["access_token"]
            token_data["refresh"] = result["refresh_token"]
            token_data["expires"] = result["expired_in"]
            with open(TOKEN_FILE, "w") as f:
                json.dump(token_data, f, indent=2)
            return token_data["access"]
        except Exception as e:
            print(f"Token refresh failed: {e}, re-login required")
    
    token_data = await login_minimax()
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    return token_data["access"]

# Add MiniMax Provider Support

## Summary

This PR adds MiniMax LLM provider support to nanobot, including OAuth authentication and OpenAI-compatible API integration.

## Changes

### 1. New Files

**`nanobot/oauth/__init__.py`**
- OAuth module initialization

**`nanobot/oauth/minimax.py`**
- MiniMax OAuth implementation
  - Device code flow for OAuth login
  - Token refresh logic
  - Token file management (~/.nanobot/.minimax_token)
  - Support for CN and Global regions

### 2. Modified Files

**`nanobot/providers/registry.py`**
- Added MiniMax ProviderSpec with OpenAI-compatible configuration
- Auto-detects API key prefix (sk-)
- Auto-configures API base (https://api.minimaxi.com/v1)
- Uses `openai/` prefix for LiteLLM routing
- Strips prefix before sending to endpoint

**`nanobot/cli/commands.py`**
- Added `oauth` subcommand with actions:
  - `login` - Start OAuth login flow
  - `status` - Check OAuth configuration status
  - `refresh` - Force refresh token
  - `token` - Get current access token

## Usage

### Quick Start

```bash
# Set environment variables
export OPENAI_API_KEY="your-minimax-api-key"
export OPENAI_API_BASE="https://api.minimaxi.com/v1"

# Or configure in ~/.nanobot/config.json
{
  "providers": {
    "minimax": {
      "apiKey": "sk-xxx",
      "apiBase": "https://api.minimaxi.com/v1"
    }
  }
}

# Chat with MiniMax
nanobot agent -m "你好" --model MiniMax-M2.1
```

### OAuth Login (for future OAuth support)

```bash
nanobot oauth login --region cn
```

## Testing

All tests passed:
- ✅ OAuth module import
- ✅ Provider registration
- ✅ LiteLLMProvider integration
- ✅ API call successful

## Notes

- MiniMax API is OpenAI-compatible, using standard Bearer token auth
- Supports both CN (api.minimaxi.com) and Global (api.minimax.io) endpoints
- LiteLLM handles model routing with `openai/` prefix
- Full OAuth implementation ready for future device code flow support

## Related

- Inspired by [OpenClaw MiniMax OAuth](https://github.com/openclaw/openclaw/tree/main/extensions/minimax-portal-auth)

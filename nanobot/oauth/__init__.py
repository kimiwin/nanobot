"""OAuth providers for nanobot."""

from .minimax import get_minimax_access_token, login_minimax

__all__ = ["get_minimax_access_token", "login_minimax"]

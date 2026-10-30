"""Runtime token authentication."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass


class AuthError(Exception):
    """Authentication or protocol negotiation failed."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TokenAuth:
    """Constant-time bearer-token verification for localhost WebSocket clients."""

    token: str

    @classmethod
    def generate(cls) -> TokenAuth:
        return cls(secrets.token_urlsafe(32))

    def verify(self, candidate: str) -> bool:
        if not candidate:
            return False
        return hmac.compare_digest(self.token, candidate)

    def require(self, candidate: str) -> None:
        if not self.verify(candidate):
            raise AuthError("auth_failed", "invalid runtime token")

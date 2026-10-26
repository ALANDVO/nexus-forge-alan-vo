"""Authentication middleware for FastAPI."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .oidc import TokenValidator, OIDCConfig, get_token_validator


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and validate OIDC tokens from Authorization header."""

    async def dispatch(self, request: Request, call_next):
        validator = get_token_validator()
        if validator is None:
            return await call_next(request)

        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            claims = await validator.validate_token(token)
            if claims:
                request.state.user = claims

        return await call_next(request)

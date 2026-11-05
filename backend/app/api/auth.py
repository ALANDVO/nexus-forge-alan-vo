"""OIDC authentication endpoints: login, callback, logout, user info."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth.oidc import (
    AuthState,
    OIDCConfig,
    build_authorization_url,
    build_logout_url,
    exchange_code_for_tokens,
    get_token_validator,
    set_token_validator,
)
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory state store for PKCE (use Redis in production)
_auth_states: dict[str, AuthState] = {}


class UserInfoResponse(BaseModel):
    sub: str
    email: str | None = None
    preferred_username: str | None = None
    roles: list[str]
    is_viewer: bool
    is_operator: bool
    is_admin: bool


def _get_oidc_config() -> OIDCConfig:
    config = OIDCConfig.from_env()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC not configured",
        )
    return config


def _get_token_validator():
    validator = get_token_validator()
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC not initialized",
        )
    return validator


def _optional_token_validator():
    """Get token validator if OIDC is configured, else None."""
    return get_token_validator()


@router.get("/login")
async def login(request: Request):
    """Initiate OIDC authorization code flow with PKCE."""
    config = _get_oidc_config()
    auth_state = AuthState.generate()
    _auth_states[auth_state.state] = auth_state

    response = RedirectResponse(url=build_authorization_url(config, auth_state))
    response.set_cookie(
        "oidc_state",
        auth_state.state,
        httponly=True,
        secure=not settings.is_demo,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Handle OIDC authorization code callback."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OIDC error: {error} - {error_description}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter",
        )

    cookie_state = request.cookies.get("oidc_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    auth_state = _auth_states.pop(state, None)
    if not auth_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expired or invalid state",
        )

    config = _get_oidc_config()
    tokens = await exchange_code_for_tokens(config, code, auth_state.code_verifier)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange code for tokens",
        )

    validator = _get_token_validator()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ID token in response",
        )

    claims = await validator.validate_token(id_token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ID token",
        )

    if claims.nonce != auth_state.nonce:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nonce mismatch",
        )

    response = RedirectResponse(url="/")
    response.set_cookie(
        "access_token",
        tokens.get("access_token", ""),
        httponly=True,
        secure=not settings.is_demo,
        samesite="lax",
        max_age=tokens.get("expires_in", 3600),
    )
    if "refresh_token" in tokens:
        response.set_cookie(
            "refresh_token",
            tokens["refresh_token"],
            httponly=True,
            secure=not settings.is_demo,
            samesite="lax",
            max_age=86400 * 30,
        )
    response.delete_cookie("oidc_state")
    return response


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Log out user and clear tokens."""
    config = _get_oidc_config()
    logout_url = build_logout_url(config, str(request.base_url))

    response = RedirectResponse(url=logout_url)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@router.get("/me", response_model=UserInfoResponse)
async def me(request: Request):
    """Get current user info from validated token."""
    validator = _get_token_validator()

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    claims = await validator.validate_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return UserInfoResponse(
        sub=claims.sub,
        email=claims.email,
        preferred_username=claims.preferred_username,
        roles=claims.roles,
        is_viewer=claims.is_viewer(),
        is_operator=claims.is_operator(),
        is_admin=claims.is_admin(),
    )


def _optional_user(request: Request):
    """Optional dependency: returns user claims if authenticated, None otherwise."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    # Note: this is sync but validate_token is async; we'll handle in async deps below
    return None  # Placeholder - actual validation in async deps


async def optional_viewer(request: Request):
    """Optional viewer dependency: validates token if present, otherwise allows."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    claims = await validator.validate_token(token)
    if not claims:
        return None

    if not claims.is_viewer():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires viewer role",
        )

    request.state.user = claims
    return claims


async def optional_operator(request: Request):
    """Optional operator dependency: validates token if present, otherwise allows."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    claims = await validator.validate_token(token)
    if not claims:
        return None

    if not claims.is_operator():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires operator role",
        )

    request.state.user = claims
    return claims


async def optional_admin(request: Request):
    """Optional admin dependency: validates token if present, otherwise allows."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None

    claims = await validator.validate_token(token)
    if not claims:
        return None

    if not claims.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires admin role",
        )

    request.state.user = claims
    return claims


# For backward compatibility - these will be used when OIDC is configured
async def require_viewer_dep(request: Request):
    """Require viewer role (enforces auth when OIDC configured)."""
    validator = _optional_token_validator()
    if validator is None:
        # OIDC not configured - allow for backward compatibility in tests
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    claims = await validator.validate_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not claims.is_viewer():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires viewer role",
        )

    request.state.user = claims
    return claims


async def require_operator_dep(request: Request):
    """Require operator role (enforces auth when OIDC configured)."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    claims = await validator.validate_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not claims.is_operator():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires operator role",
        )

    request.state.user = claims
    return claims


async def require_admin_dep(request: Request):
    """Require admin role (enforces auth when OIDC configured)."""
    validator = _optional_token_validator()
    if validator is None:
        return None

    auth_header = request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    claims = await validator.validate_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not claims.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires admin role",
        )

    request.state.user = claims
    return claims


# Export the dependencies
require_viewer = require_viewer_dep
require_operator = require_operator_dep
require_admin = require_admin_dep

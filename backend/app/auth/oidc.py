"""OIDC authentication client and token validation."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx
from jose import jwt, jwk
from jose.exceptions import JWTError
from jose.utils import base64url_decode

from ..config import settings


@dataclass
class OIDCConfig:
    issuer: str
    client_id: str
    client_secret: Optional[str] = None
    redirect_uri: str = "http://127.0.0.1:5123/callback"
    scopes: str = "openid profile email roles"

    @classmethod
    def from_env(cls) -> Optional["OIDCConfig"]:
        issuer = os.environ.get("OIDC_ISSUER", "").strip()
        client_id = os.environ.get("OIDC_CLIENT_ID", "").strip()
        if not issuer or not client_id:
            return None
        return cls(
            issuer=issuer,
            client_id=client_id,
            client_secret=os.environ.get("OIDC_CLIENT_SECRET", "").strip() or None,
            redirect_uri=os.environ.get("OIDC_REDIRECT_URI", "").strip() or "http://127.0.0.1:5123/callback",
        )


@dataclass
class AuthState:
    state: str
    nonce: str
    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"
    created_at: float = 0.0

    @classmethod
    def generate(cls) -> "AuthState":
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        return cls(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            code_challenge=code_challenge,
            created_at=time.time(),
        )


class JWKSClient:
    def __init__(self, jwks_url: str, cache_ttl: int = 3600):
        self.jwks_url = jwks_url
        self.cache_ttl = cache_ttl
        self._cache: dict = {}
        self._cache_time = 0.0

    async def get_signing_key(self, kid: str) -> Optional[jwk.Key]:
        if time.time() - self._cache_time > self.cache_ttl:
            await self._refresh()
        key_data = self._cache.get(kid)
        if key_data:
            return jwk.construct(key_data)
        return None

    async def _refresh(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self.jwks_url)
            resp.raise_for_status()
            jwks = resp.json()
            self._cache = {key["kid"]: key for key in jwks.get("keys", [])}
            self._cache_time = time.time()


class TokenValidator:
    def __init__(self, config: OIDCConfig):
        self.config = config
        self.jwks_client = JWKSClient(f"{config.issuer.rstrip('/')}/protocol/openid-connect/certs")
        self._issuer = config.issuer.rstrip("/")

    async def validate_token(self, token: str) -> Optional["TokenClaims"]:
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                return None

            signing_key = await self.jwks_client.get_signing_key(kid)
            if not signing_key:
                return None

            claims = jwt.decode(
                token,
                signing_key.to_pem().decode(),
                algorithms=["RS256"],
                audience=self.config.client_id,
                issuer=self._issuer,
                options={"verify_exp": True, "verify_iat": True},
            )
            return TokenClaims(**claims)
        except (JWTError, Exception):
            return None


@dataclass
class TokenClaims:
    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    iat: int
    nonce: Optional[str] = None
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    realm_access: Optional[dict] = None
    resource_access: Optional[dict] = None

    @property
    def roles(self) -> list[str]:
        roles = []
        if self.realm_access and "roles" in self.realm_access:
            roles.extend(self.realm_access["roles"])
        if self.resource_access:
            for client_roles in self.resource_access.values():
                if "roles" in client_roles:
                    roles.extend(client_roles["roles"])
        return list(set(roles))

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def is_viewer(self) -> bool:
        return self.has_role("viewer") or self.has_role("operator") or self.has_role("admin")

    def is_operator(self) -> bool:
        return self.has_role("operator") or self.has_role("admin")

    def is_admin(self) -> bool:
        return self.has_role("admin")


def build_authorization_url(config: OIDCConfig, state: AuthState) -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": config.scopes,
        "state": state.state,
        "nonce": state.nonce,
        "code_challenge": state.code_challenge,
        "code_challenge_method": state.code_challenge_method,
    }
    return f"{config.issuer.rstrip('/')}/protocol/openid-connect/auth?{urlencode(params)}"


async def exchange_code_for_tokens(
    config: OIDCConfig, code: str, code_verifier: str
) -> Optional[dict]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "code_verifier": code_verifier,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{config.issuer.rstrip('/')}/protocol/openid-connect/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None


async def refresh_token(config: OIDCConfig, refresh_token: str) -> Optional[dict]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{config.issuer.rstrip('/')}/protocol/openid-connect/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None


def build_logout_url(config: OIDCConfig, post_logout_redirect_uri: str = "") -> str:
    params = {"client_id": config.client_id}
    if post_logout_redirect_uri:
        params["post_logout_redirect_uri"] = post_logout_redirect_uri
    return f"{config.issuer.rstrip('/')}/protocol/openid-connect/logout?{urlencode(params)}"

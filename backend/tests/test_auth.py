"""Auth OIDC tests with mocked Keycloak."""
from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import create_app


# Generate a test RSA key pair
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

_PRIVATE_PEM = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

_PUBLIC_PEM = _public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

# JWKS format for the public key
import json
_jwk_dict = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_public_key))
_JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "alg": "RS256",
            "n": _jwk_dict["n"],
            "e": _jwk_dict["e"],
        }
    ]
}

ISSUER = "https://keycloak.test/realms/test"
CLIENT_ID = "test-client"
REDIRECT_URI = "http://127.0.0.1:5123/callback"


def _make_token(claims: dict[str, Any], kid: str = "test-key-1") -> str:
    """Create a signed JWT token for testing."""
    now = int(time.time())
    default_claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "exp": now + 3600,
        "iat": now,
        "sub": "test-user",
        "preferred_username": "testuser",
        "email": "test@example.com",
        "realm_access": {"roles": ["viewer"]},
        "nonce": "test-nonce",
    }
    default_claims.update(claims)
    return jwt.encode(default_claims, _PRIVATE_PEM, algorithm="RS256", headers={"kid": kid})


class MockJWKSClient:
    """Mock JWKS client that returns our test key."""

    def __init__(self):
        pass

    async def get_signing_key(self, kid: str):
        if kid == "test-key-1":
            from jose import jwk
            return jwk.construct(_JWKS["keys"][0])
        return None


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """Test client with OIDC configured and mocked JWKS."""
    # Enable OIDC via environment
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("OIDC_REDIRECT_URI", REDIRECT_URI)

    # Mock the JWKS client
    from app.auth.oidc import JWKSClient

    original_init = JWKSClient.__init__
    original_get_signing_key = JWKSClient.get_signing_key

    def mock_init(self, jwks_url: str, cache_ttl: int = 3600):
        self.jwks_url = jwks_url
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_time = 0.0

    async def mock_get_signing_key(self, kid: str):
        if kid == "test-key-1":
            from jose import jwk
            return jwk.construct(_JWKS["keys"][0])
        return None

    monkeypatch.setattr(JWKSClient, "__init__", mock_init)
    monkeypatch.setattr(JWKSClient, "get_signing_key", mock_get_signing_key)

    app = create_app(db_path=str(tmp_path / "test.sqlite"))
    with TestClient(app) as c:
        yield c
    app.state.storage.close()


@pytest.fixture
def no_auth_client(tmp_path):
    """Test client WITHOUT OIDC configured (backward compatibility)."""
    # Ensure OIDC is NOT configured
    for key in ["OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]:
        if key in os.environ:
            del os.environ[key]

    app = create_app(db_path=str(tmp_path / "test.sqlite"))
    with TestClient(app) as c:
        yield c
    app.state.storage.close()


def _create_plan(client: TestClient, token: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = client.post(
        "/plans", json={"name": "test plan", "text": "- [ ] task 1\n- [ ] task 2\n"}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _get_task_id(client: TestClient, plan_id: str, token: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = client.get(f"/plans/{plan_id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()["tasks"][0]["id"]


class TestBackwardCompatibility:
    """Tests that work without OIDC configured (existing behavior)."""

    def test_create_plan_without_auth(self, no_auth_client):
        plan_id = _create_plan(no_auth_client)
        assert plan_id

    def test_list_plans_without_auth(self, no_auth_client):
        _create_plan(no_auth_client)
        resp = no_auth_client.get("/plans")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_run_task_without_auth(self, no_auth_client):
        plan_id = _create_plan(no_auth_client)
        task_id = _get_task_id(no_auth_client, plan_id)
        resp = no_auth_client.post(f"/tasks/{task_id}/run", json={"command": ["true"]})
        assert resp.status_code == 200


class TestAuthEnforcement:
    """Tests that auth is enforced when OIDC is configured."""

    def test_create_plan_rejected_without_token(self, auth_client):
        resp = auth_client.post("/plans", json={"name": "test", "text": "- [ ] t\n"})
        assert resp.status_code == 401
        assert "Not authenticated" in resp.json()["detail"]

    def test_list_plans_rejected_without_token(self, auth_client):
        resp = auth_client.get("/plans")
        assert resp.status_code == 401

    def test_get_plan_rejected_without_token(self, auth_client):
        # First create a plan with a valid token (we need one to create)
        # Since we can't create without auth, this tests that we can't even access
        resp = auth_client.get("/plans/some-id")
        assert resp.status_code == 401

    def test_run_task_rejected_without_token(self, auth_client):
        resp = auth_client.post("/tasks/some-id/run", json={"command": ["true"]})
        assert resp.status_code == 401

    def test_results_rejected_without_token(self, auth_client):
        resp = auth_client.get("/results")
        assert resp.status_code == 401

    def test_classify_rejected_without_token(self, auth_client):
        resp = auth_client.post("/classify", json={"text": "test"})
        assert resp.status_code == 401

    def test_classify_metrics_rejected_without_token(self, auth_client):
        resp = auth_client.get("/classify/metrics")
        assert resp.status_code == 401


class TestValidTokenAccess:
    """Tests that valid tokens grant access."""

    def test_viewer_can_read_plans(self, auth_client):
        # Create plan with operator token, then read with viewer
        operator_token = _make_token({"realm_access": {"roles": ["operator"]}})
        plan_id = _create_plan(auth_client, operator_token)

        viewer_token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_viewer_can_get_plan(self, auth_client):
        # Create plan with operator token, then read with viewer
        operator_token = _make_token({"realm_access": {"roles": ["operator"]}})
        plan_id = _create_plan(auth_client, operator_token)

        viewer_token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get(f"/plans/{plan_id}", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200
    def test_viewer_can_list_results(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/results", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_viewer_can_classify(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.post(
            "/classify", json={"text": "# pass 1\n# fail 0\n# duration_ms 10"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_viewer_can_get_metrics(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/classify/metrics", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestRoleBasedAccess:
    """Tests for role-based authorization."""

    def test_viewer_cannot_create_plan(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.post(
            "/plans", json={"name": "test", "text": "- [ ] t\n"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert "Requires operator role" in resp.json()["detail"]

    def test_viewer_cannot_run_task(self, auth_client):
        # Need operator to create plan first
        operator_token = _make_token({"realm_access": {"roles": ["operator"]}})
        plan_id = _create_plan(auth_client, operator_token)
        task_id = _get_task_id(auth_client, plan_id, operator_token)

        # Viewer tries to run
        viewer_token = _make_token({"realm_access": {"roles": ["viewer"]}})
        resp = auth_client.post(
            f"/tasks/{task_id}/run", json={"command": ["true"]}, headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert resp.status_code == 403
        assert "Requires operator role" in resp.json()["detail"]

    def test_operator_can_create_plan(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["operator"]}})
        plan_id = _create_plan(auth_client, token)
        assert plan_id

    def test_operator_can_run_task(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["operator"]}})
        plan_id = _create_plan(auth_client, token)
        task_id = _get_task_id(auth_client, plan_id, token)

        resp = auth_client.post(
            f"/tasks/{task_id}/run", json={"command": ["true"]}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_admin_can_do_everything(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["admin"]}})
        plan_id = _create_plan(auth_client, token)
        task_id = _get_task_id(auth_client, plan_id, token)

        resp = auth_client.post(
            f"/tasks/{task_id}/run", json={"command": ["true"]}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_resource_access_roles(self, auth_client):
        """Test roles from resource_access (client-specific roles)."""
        token = _make_token(
            {
                "realm_access": {"roles": []},
                "resource_access": {CLIENT_ID: {"roles": ["operator"]}},
            }
        )
        plan_id = _create_plan(auth_client, token)
        assert plan_id


class TestInvalidTokens:
    """Tests for invalid/expired tokens."""

    def test_expired_token_rejected(self, auth_client):
        token = _make_token({"exp": int(time.time()) - 3600, "realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json()["detail"]

    def test_wrong_issuer_rejected(self, auth_client):
        token = _make_token({"iss": "https://wrong.issuer", "realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_audience_rejected(self, auth_client):
        token = _make_token({"aud": "wrong-client", "realm_access": {"roles": ["viewer"]}})
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_unknown_kid_rejected(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}}, kid="unknown-key")
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_malformed_token_rejected(self, auth_client):
        resp = auth_client.get("/plans", headers={"Authorization": "Bearer not.a.valid.token"})
        assert resp.status_code == 401


class TestAuthEndpoints:
    """Tests for /auth endpoints."""

    def test_login_redirects(self, auth_client):
        resp = auth_client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 307
        assert "location" in resp.headers
        assert ISSUER in resp.headers["location"]
        assert "code_challenge" in resp.headers["location"]
        assert "state" in resp.headers["location"]
        assert "nonce" in resp.headers["location"]

    def test_me_requires_auth(self, auth_client):
        resp = auth_client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_returns_user_info(self, auth_client):
        token = _make_token(
            {
                "realm_access": {"roles": ["viewer", "operator"]},
                "preferred_username": "testuser",
                "email": "test@example.com",
                "sub": "user-123",
            }
        )
        resp = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sub"] == "user-123"
        assert data["preferred_username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert data["is_viewer"] is True
        assert data["is_operator"] is True
        assert data["is_admin"] is False

    def test_logout_redirects(self, auth_client):
        resp = auth_client.post("/auth/logout", follow_redirects=False)
        assert resp.status_code == 307
        assert "location" in resp.headers
        assert ISSUER in resp.headers["location"]
        assert CLIENT_ID in resp.headers["location"]


class TestCookieAuth:
    """Tests for cookie-based authentication."""

    def test_cookie_token_works(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}})
        auth_client.cookies.set("access_token", token)
        resp = auth_client.get("/plans")
        assert resp.status_code == 200

    def test_bearer_priority_over_cookie(self, auth_client):
        # Set a viewer cookie
        viewer_token = _make_token({"realm_access": {"roles": ["viewer"]}})
        auth_client.cookies.set("access_token", viewer_token)

        # But send an operator bearer token
        operator_token = _make_token({"realm_access": {"roles": ["operator"]}})
        resp = auth_client.post(
            "/plans",
            json={"name": "test", "text": "- [ ] t\n"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        # Should use bearer token (operator) and succeed
        assert resp.status_code == 201


class TestAuthStatePersistence:
    """Test that auth state works across requests."""

    def test_state_stored_in_request(self, auth_client):
        token = _make_token({"realm_access": {"roles": ["viewer"]}, "sub": "user-456"})
        resp = auth_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        # The middleware should have set request.state.user
        # We can't directly test this but we can verify the token was validated
        # by checking that a subsequent request with same token works


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


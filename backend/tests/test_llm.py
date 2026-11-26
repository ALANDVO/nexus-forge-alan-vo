"""Targeted tests for the opt-in LLM explain endpoint.

These tests use the `client` fixture from conftest.py (which provides tmp_path)
and verify the LLM explain endpoint behavior.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


# ---------------------------------------------------------------------------
# Helper log snippets (same as used by the classifier dataset)
# ---------------------------------------------------------------------------
PASS_LOG = "# pass 4\n# fail 0\n# duration_ms 52"
FAIL_LOG = "# fail 2\n# duration_ms 10"


@pytest.fixture
def client(tmp_path):  # built-in pytest fixture; same pattern as test_api.py
    app = create_app(db_path=str(tmp_path / "test.sqlite"))
    with TestClient(app) as c:
        yield c
    app.state.storage.close()


# ---------------------------------------------------------------------------
# Test 1: No LLM_API_KEY → deterministic placeholder
# ---------------------------------------------------------------------------
def test_llm_explain_without_key_returns_placeholder(client):
    """When LLM_API_KEY is not set, the endpoint returns a deterministic placeholder."""
    # Ensure key is absent for this test's process
    env = dict(os.environ)
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_MODEL", None)
    os.environ.pop("LLM_BASE_URL", None)

    # The client fixture already has a tmp_path'd db
    resp = client.post("/classify/explain", json={"text": PASS_LOG})
    assert resp.status_code == 200
    body = resp.json()
    # Placeholder should mention no API key / disabled
    assert "disabled" in body["summary"].lower() or "no key" in body["summary"].lower(), (
        f"Expected placeholder mentioning disabled/no key, got: {body['summary']}"
    )
    # Classification data should still be present
    assert body["classifier_label"] == "passed"
    assert body["classifier_passed"] is True


# ---------------------------------------------------------------------------
# Test 2: With LLM_API_KEY but no provider deps → graceful degraded message
# ---------------------------------------------------------------------------
def test_llm_explain_with_key_no_deps_returns_degraded(client, monkeypatch):
    """When LLM_API_KEY is set but no adapter deps (httpx/anthropic) are installed,
    the endpoint returns a redacted graceful-degraded message."""
    os.environ["LLM_API_KEY"] = "sk-test-dummy-key-1234567890"
    os.environ["LLM_PROVIDER"] = "openai-compatible"
    os.environ["LLM_MODEL"] = "gpt-3.5-turbo"

    import sys
    # Remove any cached relevant modules so the adapter falls back to stub
    for mod in list(sys.modules.keys()):
        if "httpx" in mod or "anthropic" in mod or "google" in mod or "llm" in mod:
            del sys.modules[mod]

    # The client fixture has its own db; we reuse it but with overridden env
    resp = client.post("/classify/explain", json={"text": FAIL_LOG})
    assert resp.status_code == 200
    body = resp.json()
    # Should not crash; should return a redacted error message
    assert "advisory" in body["summary"].lower() or "error" in body["summary"].lower() or \
        "timeout" in body["summary"].lower() or "provider" in body["summary"].lower(), (
            f"Expected advisory/error message, got: {body['summary']}"
        )
    # Classification data should still be present
    assert body["classifier_label"] == "failed"
    assert body["classifier_passed"] is False


# ---------------------------------------------------------------------------
# Test 3: Endpoint always returns valid envelope (with no key)
# ---------------------------------------------------------------------------
def test_llm_explain_returns_valid_envelope_no_key(client):
    """The explain endpoint returns a valid envelope even when no key is configured."""
    env = dict(os.environ)
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_MODEL", None)
    os.environ.pop("LLM_BASE_URL", None)

    resp = client.post("/classify/explain", json={"text": PASS_LOG})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    # Validate required fields per LlmExplainResponse
    assert "summary" in body, f"Missing 'summary' in {body}"
    assert "classifier_label" in body, f"Missing 'classifier_label' in {body}"
    assert "classifier_passed" in body, f"Missing 'classifier_passed' in {body}"
    assert "classifier_confidence" in body, f"Missing 'classifier_confidence' in {body}"
    assert "classifier_agreement" in body, f"Missing 'classifier_agreement' in {body}"
    assert "provider" in body, f"Missing 'provider' in {body}"
    assert "model" in body, f"Missing 'model' in {body}"
    # Summary should be a non-empty string
    assert isinstance(body["summary"], str), f"Summary should be str, got {type(body['summary'])}"
    assert len(body["summary"]) > 0, "Summary should be non-empty"


# ---------------------------------------------------------------------------
# Test 4: Classifier result wired correctly (no key)
# ---------------------------------------------------------------------------
def test_llm_explain_classifier_wired(client):
    """The classifier result (label, passed, confidence, agreement) is correctly
    reflected in the response, matching the underlying classifier output."""
    env = dict(os.environ)
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_MODEL", None)
    os.environ.pop("LLM_BASE_URL", None)

    # Test with a pass log
    resp = client.post("/classify/explain", json={"text": PASS_LOG})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classifier_label"] == "passed", f"Expected passed, got {body['classifier_label']}"
    assert body["classifier_passed"] is True

    # Test with a fail log
    resp = client.post("/classify/explain", json={"text": FAIL_LOG})
    assert resp.status_code == 200
    body = resp.json()
    assert body["classifier_label"] == "failed", f"Expected failed, got {body['classifier_label']}"
    assert body["classifier_passed"] is False

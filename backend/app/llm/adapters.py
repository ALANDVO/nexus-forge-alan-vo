"""Opt-in LLM provider adapters for advisory explanations.

All adapters share the same contract: given a log text and optional classifier
result, return a short natural-language explanation.  Adaptation is advisory-only;
the classifier exit-code/label is authoritative.

Only the API key (`LLM_API_KEY`) is a required credential.  All other settings
(`LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`) are optional non-secret settings.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Dict, Any

from ..core.classifier import classify_outcome
from ..config import settings


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------

class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil the request."""


def _timeout_deadline(timeout_seconds: Optional[int]) -> float:
    """Compute an absolute deadline from an optional timeout."""
    if timeout_seconds is None or timeout_seconds <= 0:
        return float("inf")
    return time.time() + timeout_seconds


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

_PROVIDERS: Dict[str, Any] = {}


def register_provider(name: str, factory) -> None:
    """Register an LLM provider adapter factory."""
    _PROVIDERS[name] = factory


def get_provider(name: Optional[str] = None):
    """Get a provider instance by name, respecting settings.

    Raises ProviderError if the provider is not configured or not registered.
    """
    name = name or settings.llm.provider
    if not settings.llm.is_configured:
        raise ProviderError("LLM not configured: set LLM_API_KEY")
    if name not in _PROVIDERS:
        raise ProviderError(f"Unknown LLM provider: {name}")
    return _PROVIDERS[name]()


# ---------------------------------------------------------------------------
# Default adapters (stubs; filled in by callers who install deps)
# ---------------------------------------------------------------------------

def _default_adapter(log_text: str, classifier_result: Optional[tuple]) -> str:
    """Return a deterministic advisory placeholder when no provider is available."""
    label, passed, confidence, agreement = classifier_result or ("unknown", False, 0.0, "classifier-only")
    return (
        f"[LLM advisory disabled – no API key; classifier: {label}, "
        f"confidence={confidence:.2f}, agreement={agreement}]"
    )


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter (requires `httpx`)
# ---------------------------------------------------------------------------

try:
    import httpx  # type: ignore

    class OpenAICompatibleAdapter:
        """Adapter for any OpenAI-compatible API (LiteLLM, OpenRouter, Ollama, etc.).

        The base URL may be set via LLM_BASE_URL env var or defaults per provider.
        """

        def __init__(self) -> None:
            self.api_key = settings.llm.api_key
            self.provider = settings.llm.provider
            self.model = settings.llm.model
            base = settings.llm.base_url or self._default_base()
            self.base_url = base.rstrip("/")
            self.timeout = 30  # seconds

        def _default_base(self) -> str:
            """Per-provider default base URL."""
            defaults = {
                "openai-compatible": "https://api.openai.com/v1",
                "anthropic": "https://api.anthropic.com",
                "gemini": "https://generativelanguage.googleapis.com",
                "ollama": "http://127.0.0.1:11434",
            }
            return defaults.get(self.provider, "https://api.openai.com/v1")

        def explain(self, log_text: str, classifier_result: Optional[tuple], timeout: Optional[int] = None) -> str:
            """Request an advisory explanation from the provider.

            Returns the model's natural-language summary or a redacted error message.
            """
            deadline = _timeout_deadline(timeout or self.timeout)
            classifier_label, _, classifier_confidence, classifier_agreement = (
                classifier_result or ("unknown", False, 0.0, "classifier-only")
            )

            # Build the minimal prompt grounded in the classifier output and log
            prompt = (
                f"You are an observability assistant for a plan-execution ledger. "
                f"Here is a classifier assessment of the run: label={classifier_label}, "
                f"confidence={classifier_confidence:.2f}, agreement={classifier_agreement}. "
                f"Here is the captured log (truncated to 800 chars):\n"
                f"{log_text[:800]}\n"
                f"Please give a one-sentence advisory summary of whether the plan step passed or failed, "
                f"any notable patterns, and if any re-run may be warranted. Keep it concise, "
                f"and do NOT include any credentials, passwords, or raw token values."
            )

            messages = [
                {"role": "system", "content": "You are a concise observability assistant. "
                                               "Reply only in English. Do not emit credentials."},
                {"role": "user", "content": prompt},
            ]

            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json={"model": self.model, "messages": messages},
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    timeout=min(time.time() + self.timeout - time.time(), self.timeout),
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    # Redact: key is bad; return a generic advisory message
                    return "[LLM advisory: authentication failed – check LLM_API_KEY and provider config]"
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Redact any accidental key-like strings
                return self._redact(content)
            except httpx.TimeoutException:
                return "[LLM advisory: request timed out – consider increasing timeout or checking connectivity]"
            except httpx.HTTPStatusError as exc:
                # 4xx/5xx from the provider – return redacted error, never leak key
                body = exc.response.text[:200] if exc.response else ""
                return f"[LLM advisory: provider error {exc.response.status_code if exc.response else '?'}: {self._redact(body)}]"
            except Exception as exc:  # broad: network, DNS, etc.
                return f"[LLM advisory: unexpected error {self._redact(str(exc))}]"

        @staticmethod
        def _redact(text: str) -> str:
            """Remove anything that looks like a secret key from the response."""
            import re
            # Common patterns – be conservative so we don't accidentally strip useful text
            return re.sub(r"sk-[a-zA-Z0-9]{20,}|token[=\s][^\s]{20,}|password[=\s][^\s]{10,}", "<redacted>", text)

except ImportError:  # httpx not installed
    OpenAICompatibleAdapter = None  # type: ignore


# ---------------------------------------------------------------------------
# Anthropic adapter (stub; requires `anthropic` package)
# ---------------------------------------------------------------------------

try:
    from anthropic import Anthropic  # type: ignore

    class AnthropicAdapter:
        """Adapter for Anthropic's Messages API."""

        def __init__(self) -> None:
            self.api_key = settings.llm.api_key
            self.model = settings.llm.model
            self.base_url = settings.llm.base_url or "https://api.anthropic.com"
            self.timeout = 30

        def explain(self, log_text: str, classifier_result: Optional[tuple], timeout: Optional[int] = None) -> str:
            deadline = _timeout_deadline(timeout or self.timeout)
            classifier_label, _, classifier_confidence, classifier_agreement = (
                classifier_result or ("unknown", False, 0.0, "classifier-only")
            )
            prompt = (
                f"Summarize in one sentence the outcome of this plan execution step. "
                f"Classifier says: label={classifier_label}, confidence={classifier_confidence:.2f}. "
                f"Log (first 800 chars):\n{log_text[:800]}\n"
                f"Reply concisely in English. Do not emit credentials or tokens."
            )
            try:
                client = Anthropic(api_key=self.api_key)
                resp = client.messages.create(
                    model=self.model,
                    max_tokens=128,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = resp.content[0].text.strip()
                return OpenAICompatibleAdapter._redact(content)  # reuse redact
            except Exception as exc:  # broad
                return f"[LLM advisory: unexpected error {OpenAICompatibleAdapter._redact(str(exc))}]"

except ImportError:  # anthropic not installed
    AnthropicAdapter = None  # type: ignore


# ---------------------------------------------------------------------------
# Gemini adapter (stub; requires `google-generativeai` package)
# ---------------------------------------------------------------------------

try:
    import google.generativeai as genai  # type: ignore

    class GeminiAdapter:
        """Adapter for Google Gemini generateContent API."""

        def __init__(self) -> None:
            self.api_key = settings.llm.api_key
            self.model = settings.llm.model
            genai.configure(api_key=self.api_key)
            self.base_url = settings.llm.base_url or "https://generativelanguage.googleapis.com/v1"
            self.timeout = 30

        def explain(self, log_text: str, classifier_result: Optional[tuple], timeout: Optional[int] = None) -> str:
            classifier_label, _, classifier_confidence, classifier_agreement = (
                classifier_result or ("unknown", False, 0.0, "classifier-only")
            )
            prompt = (
                f"Given the classifier assessment (label={classifier_label}, "
                f"confidence={classifier_confidence:.2f}) and the log below (first 800 chars):\n"
                f"{log_text[:800]}\n"
                f"Produce a single English sentence summarizing whether the plan step passed or failed, "
                f"any notable patterns, and whether a re-run seems warranted. "
                f"Do not include credentials or tokens."
            )
            try:
                model = genai.GenerativeModel(self.model)
                resp = model.generate_content(
                    prompt,
                    request_options={"timeout": timeout or self.timeout},
                )
                text = resp.text.strip()
                return OpenAICompatibleAdapter._redact(text)  # reuse redact
            except Exception as exc:  # broad
                return f"[LLM advisory: unexpected error {OpenAICompatibleAdapter._redact(str(exc))}]"

except ImportError:  # google-generativeai not installed
    GeminiAdapter = None  # type: ignore


# ---------------------------------------------------------------------------
# Ollama adapter (stub; requires `httpx`)
# ---------------------------------------------------------------------------

try:
    import httpx  #  type: ignore

    class OllamaAdapter:
        """Adapter for local Ollama inference server."""

        def __init__(self) -> None:
            self.base_url = settings.llm.base_url or "http://127.0.0.1:11434"
            self.model = settings.llm.model or "llama2"
            self.timeout = 60

        def explain(self, log_text: str, classifier_result: Optional[tuple], timeout: Optional[int] = None) -> str:
            deadline = _timeout_deadline(timeout or self.timeout)
            classifier_label, _, classifier_confidence, classifier_agreement = (
                classifier_result or ("unknown", False, 0.0, "classifier-only")
            )
            prompt = (
                f"You are an observability assistant. Given the classifier result "
                f"(label={classifier_label}, confidence={classifier_confidence:.2f}) and this log (first 800 chars):\n"
                f"{log_text[:800]}\n"
                f"Give a one-sentence advisory summary of the plan step outcome: passed or failed, "
                f"notable patterns, and if a re-run may be needed. Keep it concise, in English. "
                f"Do not emit credentials."
            )
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
                    timeout=timeout or self.timeout,
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    return "[LLM advisory: authentication failed – check LLM_API_KEY and provider config]"
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                return OpenAICompatibleAdapter._redact(content)
            except httpx.TimeoutException:
                return "[LLM advisory: request timed out – consider increasing timeout or checking connectivity]"
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:200] if exc.response else ""
                return f"[LLM advisory: provider error {exc.response.status_code if exc.response else '?'}: {OpenAICompatibleAdapter._redact(body)}]"
            except Exception as exc:
                return f"[LLM advisory: unexpected error {OpenAICompatibleAdapter._redact(str(exc))}]"

except ImportError:  # httpx not installed
    OllamaAdapter = None  # type: ignore


# ---------------------------------------------------------------------------
# Public helper: advisory explanation
# ---------------------------------------------------------------------------

def explain(log_text: str, classifier_result: Optional[tuple] = None, timeout: Optional[int] = None) -> str:
    """Return an advisory LLM explanation for a log entry.

    This is **advisory only**: the classifier label/exit code is authoritative.
    If no API key is configured, a deterministic placeholder is returned.
    If a provider is configured but unavailable, a redacted error message is returned.

    Parameters
    ----------
    log_text : str
        The captured stdout+stderr from the task execution.
    classifier_result : tuple | None
        Result of ``classify_outcome`` (label, passed, confidence, agreement).
        If ``None``, the classifier is run automatically.
    timeout : int | None
        Maximum seconds to wait for the provider response.  Defaults to provider-specific
        default; ``None`` means no wall-clock timeout enforced beyond the SDK default.

    Returns
    -------
    str
        Natural-language advisory summary, or a redacted error/message indicating
        why advisory could not be produced.
    """
    # If classifier not provided, run it
    if classifier_result is None:
        from ..core import classifier
        classifier_result = classifier.classify_outcome(
            exit_code=None, log_text=log_text
        )

    # If LLM not configured, return deterministic placeholder
    if not settings.llm.is_configured:
        return _default_adapter(log_text, classifier_result)

    # Dispatch to the registered provider
    try:
        provider = get_provider()
        return provider.explain(log_text, classifier_result, timeout)
    except ProviderError as exc:
        return f"[LLM advisory: {exc}]"

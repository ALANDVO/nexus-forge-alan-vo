"""Application configuration sourced from the environment.

Operator-controlled (never request input from end users). Demo mode is explicit
and refuses to start in production. See README "Security" section.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = str(DATA_DIR / "ledger.sqlite")


def resolve_db_path() -> str:
    """Read the DB path at call time so tests/deployment can override via env."""
    return os.environ.get("NEXUS_DB_PATH") or DEFAULT_DB_PATH


@dataclass(frozen=True)
class LlmSettings:
    """LLM provider configuration (opt-in advisory explanations).
    
    Only LLM_API_KEY is required; all other settings are optional non-secret settings.
    When the key is empty, all LLM endpoints return advisory-disabled responses.
    """
    api_key: str = ""  # set via LLM_API_KEY env var; empty = disabled
    provider: str = "openai-compatible"  # openai-compatible, anthropic, gemini, ollama
    model: str = "gpt-3.5-turbo"  # model name, optional
    base_url: str = ""  # optional override for provider base URL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def is_disabled(self) -> bool:
        return not self.is_configured


@dataclass(frozen=True)
class Settings:
    db_path: str = ""
    version: str = "0.1.0"
    run_timeout_seconds: int = 120
    max_run_timeout_seconds: int = 300
    llm: LlmSettings = None  # type: ignore

    @property
    def is_demo(self) -> bool:
        """Local-only demo mode. Must be explicitly selected; refuses in production."""
        env = os.environ.get("NEXUS_ENV", "production")
        return env == "dev" and os.environ.get("NEXUS_DEMO", "0") == "1"


# Initialise LLM settings from environment
_llm_key = os.environ.get("LLM_API_KEY", "")
_llm_provider = os.environ.get("LLM_PROVIDER", "openai-compatible")
_llm_model = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")
_llm_base_url = os.environ.get("LLM_BASE_URL", "")

settings = Settings(
    db_path=resolve_db_path(),
    llm=LlmSettings(
        api_key=_llm_key,
        provider=_llm_provider,
        model=_llm_model,
        base_url=_llm_base_url,
    ),
)

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
class Settings:
    db_path: str = ""
    version: str = "0.1.0"
    run_timeout_seconds: int = 120
    max_run_timeout_seconds: int = 300

    @property
    def is_demo(self) -> bool:
        """Local-only demo mode. Must be explicitly selected; refuses in production."""
        env = os.environ.get("NEXUS_ENV", "production")
        return env == "dev" and os.environ.get("NEXUS_DEMO", "0") == "1"


settings = Settings(db_path=resolve_db_path())
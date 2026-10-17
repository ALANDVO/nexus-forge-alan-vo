"""Structured in-process audit logging (JSON lines to stderr).

Never logs tokens or credentials. Complements the on-disk audit table in
:mod:`app.services.storage`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("nexus.audit")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(action: str, detail: dict | None = None) -> None:
    """Emit one structured audit event as a single JSON line to stderr."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
    _logger.info(json.dumps({"ts": _now(), "action": action, "detail": detail or {}}, sort_keys=True))
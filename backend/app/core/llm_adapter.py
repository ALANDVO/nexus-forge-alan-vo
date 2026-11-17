"""LLM adapter for advisory explanations."""
from __future__ import annotations

import os
from typing import Optional

class LLMAdapter:
    """Generate advisory explanations using LLM."""
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.provider = os.getenv("LLM_PROVIDER", "openai-compatible")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("LLM_BASE_URL")

    def advisory_explanation(self, log_text: str, label: str, passed: bool, confidence: float,
                             agreement: str, exit_code: Optional[int], duration_ms: int,
                             last_line: str, head: str) -> str:
        """Return an advisory explanation for the given outcome."""
        if not self.api_key:
            return ""
        # TODO: implement actual LLM call
        return f"Advisory: {label} (passed={passed}) based on log."

adapter = LLMAdapter()

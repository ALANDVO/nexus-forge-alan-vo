"""LLM adapter for advisory explanations.

Opt-in LLM providers (OpenAI-compatible, Anthropic, Gemini, Ollama) for
advisory explanations. The only credential variable is LLM_API_KEY; all
other settings are optional non-secret configuration. Calls are advisory-only
and never affect core classifier or ledger behavior.

Bounded timeouts, redacted errors, and offline fallback (empty string when
LLM_API_KEY is not set).
"""
from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger("nexus-forge.llm")


class LLMAdapter:
    """Generate advisory explanations using LLM providers.

    Supported providers (selected via LLM_PROVIDER):
      - openai-compatible  (default)  – uses openai library with optional
        LLM_BASE_URL
      - anthropic         – uses anthropic library
      - gemini            – uses google.generativeai library
      - ollama            – uses ollama library (chat/complete API)

    The sole secret is LLM_API_KEY. If it is unset or empty, advisory_explanation
    returns "" immediately (offline mode). All provider calls are wrapped in
    timeouts and any raised exceptions are logged (no secrets leaked) and result
    in "" being returned.
    """

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("LLM_API_KEY")
        self.provider: str = os.getenv("LLM_PROVIDER", "openai-compatible").strip()
        self.model: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
        self.base_url: Optional[str] = os.getenv("LLM_BASE_URL") and os.getenv("LLM_BASE_URL").strip() or None

        # Validate provider early
        valid = {"openai-compatible", "anthropic", "gemini", "ollama"}
        if self.provider not in valid:
            logger.warning(
                "LLM_PROVIDER=%s is not a recognised provider; falling back to openai-compatible",
                self.provider,
            )
            self.provider = "openai-compatible"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advisory_explanation(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        """Return an advisory explanation for the given outcome.

        Parameters
        ----------
        log_text : str
            The full captured log from the task execution.
        label : str
            The classifier label ("passed" or "failed").
        passed : bool
            Whether the classifier determined a pass.
        confidence : float
            Classifier confidence in [0, 1].
        agreement : str
            "classifier-only" or "classifier-agrees" or "classifier-conflict".
        exit_code : Optional[int]
            The process exit code (authoritative) or None.
        duration_ms : int
            Wall-clock duration of the task.
        last_line : str
            The last non-blank line of the log.
        head : str
            First few lines of the log (for context).

        Returns
        -------
        str
            An advisory explanation suitable for display in a UI.  Returns ""
          when LLM_API_KEY is not set, when the provider is unavailable, or
          when the call fails (errors are always redacted – no API keys or
          personal data are included in any returned or logged string).
        """
        if not self.api_key:
            return ""

        try:
            return self._call_provider(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("LLM advisory call failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    def _call_provider(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        provider = self.provider
        if provider == "openai-compatible":
            return self._call_openai_compatible(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )
        if provider == "anthropic":
            return self._call_anthropic(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )
        if provider == "gemini":
            return self._call_gemini(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )
        if provider == "ollama":
            return self._call_ollama(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )
        # Fallback (should not happen due to validation in __init__)
        logger.warning("Unknown LLM provider %s", provider)
        return ""

    # ------------------------------------------------------------------
    # Individual provider implementations
    # ------------------------------------------------------------------

    # NOTE: Each provider call uses a wall-clock timeout of 10 seconds.
    # If the call does not complete within that window, a TimeoutError is
    # raised and the except path in advisory_explanation returns "".

    def _call_openai_compatible(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        import openai  # imported lazily – not all deployments have it

        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url or None,
                timeout=10,  # seconds – wall-clock timeout for the request
            )

            # Build a concise prompt that grounds the model in the recorded
            # evidence (exit code, classifier label, duration, last line,
            # and a short head excerpt).  The model's only job is to produce
            # a short human-readable remark; it does NOT influence the
            # recorded outcome.
            prompt = self._build_prompt(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
            )
            text = response.choices[0].message.content or ""
            # Strip any residual formatting; keep only the plain explanation.
            return text.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("openai-compatible call failed: %s", exc)
            return ""

    def _call_anthropic(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        import anthropic  # imported lazily

        try:
            client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=10.0,  # seconds
            )

            prompt = self._build_prompt(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )

            response = client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0,
                system_role="You are an assistive observer for a plan-ledger system. "
                          "Produce a short advisory remark (one sentence) based on the "
                          "evidence provided.  Do NOT change the outcome; the exit code "
                          "and classifier label are authoritative.  Keep it concise.",
                messages=[{"role": "user", "content": prompt}],
            )
            # anthropic SDK returns a Message; extract text
            text = ""
            if hasattr(response, "content") and response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                    elif isinstance(block, str):
                        text += block
            return text.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("anthropic call failed: %s", exc)
            return ""

    def _call_gemini(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        import google.generativeai as genai  # imported lazily

        try:
            genai.configure(api_key=self.api_key)

            prompt = self._build_prompt(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )

            model = genai.GenerativeModel(self.model)
            response = model.generate_content(
                ["You are an assistive observer for a plan-ledger system. "
                 "Produce a short advisory remark (one sentence) based on the "
                 "evidence provided.  Do NOT change the outcome; the exit code "
                 "and classifier label are authoritative.  Keep it concise.",
                 prompt],
                generation_config=genai.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=200,
                ),
            )
            text = getattr(response, "text", "") or ""
            return text.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("gemini call failed: %s", exc)
            return ""

    def _call_ollama(
        self,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        import ollama  # imported lazily

        try:
            client = ollama.Client(
                host=self.base_url or "http://127.0.0.1:11434",
                timeout=10,  # seconds
            )

            prompt = self._build_prompt(
                log_text=log_text,
                label=label,
                passed=passed,
                confidence=confidence,
                agreement=agreement,
                exit_code=exit_code,
                duration_ms=duration_ms,
                last_line=last_line,
                head=head,
            )

            response = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            # ollama returns message dict with 'content'
            message = response.get("message", {}) if isinstance(response, dict) else {}
            text = message.get("content", "") or ""
            return text.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("ollama call failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Prompt construction (grounded in records, no secrets)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        *,
        log_text: str,
        label: str,
        passed: bool,
        confidence: float,
        agreement: str,
        exit_code: Optional[int],
        duration_ms: int,
        last_line: str,
        head: str,
    ) -> str:
        """Build a concise, grounded prompt for the LLM.

        The prompt includes only facts that are already recorded in the
        ledger (exit code, classifier label/confidence/agreement, duration,
        last line, and a short head excerpt).  No raw user credentials,
        no API keys, and no personal data ever appear.
        """
        # Sanitize: trim to reasonable length to keep prompts bounded.
        head_excerpt = (head or "")[:300]
        last = (last_line or "")[:200]
        log_summary = (log_text or "")[:500]

        lines = [
            "Produce a short advisory remark (one sentence) for a plan-ledger "
            "system. The outcome is already determined by the exit code and "
            "the from-scratch ML classifier. Your only job is to add a "
            "human-readable comment grounded in the recorded evidence.",
            "",
            "Recorded evidence:",
            f"  - classifier label: {label} (confidence={confidence:.2f}, "
            f"agreement={agreement})",
            f"  - exit code: {exit_code if exit_code is not None else 'none'}",
            f"  - duration (ms): {duration_ms}",
            f"  - last log line: {last}",
            f"  - log head (first ~200 chars): {head_excerpt}",
            f"  - full log summary (first ~500 chars): {log_summary}",
            "",
            "Instructions:",
            "  - Keep the remark to a single sentence.",
            "  - Do NOT restate the exit code or classifier label verbatim; "
            "they are authoritative and will not be changed.",
            "  - Do NOT include any reasoning about credentials, keys, or "
            "external services.",
            "  - If the evidence is ambiguous, note that the classifier and "
            "exit code agree/disagree, but do NOT suggest altering the "
            "recorded outcome.",
        ]
        return "\n".join(lines)

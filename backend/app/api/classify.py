"""ML classifier inspection and evaluation endpoints (opt-in, advisory)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.auth import require_viewer
from ..core import classifier
from ..config import settings
from ..llm.adapters import explain, ProviderError

router = APIRouter(prefix="/classify", tags=["classifier"])


class ClassifyRequest(BaseModel):
    text: str


class ClassifyResponse(BaseModel):
    label: str
    passed: bool
    confidence: float
    agreement: str


class LlmExplainRequest(BaseModel):
    """Request advisory LLM explanation for a log entry."""
    text: str
    timeout: int | None = None  # optional override in seconds


class LlmExplainResponse(BaseModel):
    """Advisory LLM explanation response."""
    summary: str
    classifier_label: str
    classifier_passed: bool
    classifier_confidence: float
    classifier_agreement: str
    provider: str
    model: str


class MetricsResponse(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1: float
    train_size: int
    test_size: int
    tp: int
    fp: int
    tn: int
    fn: int
    dataset_size: int
    note: str = "deterministic split of the bundled hand-labeled runner dataset"


@router.post("", response_model=ClassifyResponse)
def classify(
    body: ClassifyRequest,
    _user=Depends(require_viewer),
):
    label, passed, confidence, agreement = classifier.classify_outcome(
        exit_code=None, log_text=body.text
    )
    return ClassifyResponse(label=label, passed=passed, confidence=confidence, agreement=agreement)


@router.post("/explain", response_model=LlmExplainResponse)
def llm_explain(
    body: LlmExplainRequest,
    _user=Depends(require_viewer),
):
    """Advisory LLM explanation for a log entry.

    This endpoint is opt-in and requires ``LLM_API_KEY`` to be set.
    The classifier label/exit code is authoritative; this is a natural-language
    supplement only.  Bounded timeouts and redacted errors are enforced.

    Returns a deterministic placeholder when no key is configured, and a
    provider-specific summary when a key is available.
    """
    # Run classifier automatically if not already done
    classifier_result = classifier.classify_outcome(
        exit_code=None, log_text=body.text
    )

    # Get advisory explanation (handles no-key, timeout, errors)
    summary = explain(
        log_text=body.text,
        classifier_result=classifier_result,
        timeout=body.timeout,
    )

    label, passed, confidence, agreement = classifier_result

    return LlmExplainResponse(
        summary=summary,
        classifier_label=label,
        classifier_passed=passed,
        classifier_confidence=confidence,
        classifier_agreement=agreement,
        provider=settings.llm.provider,
        model=settings.llm.model,
    )


@router.get("/metrics", response_model=MetricsResponse)
def metrics(
    _user=Depends(require_viewer),
):
    m = classifier.evaluate()
    m["dataset_size"] = len(classifier.DATASET)
    return MetricsResponse(**m)


@router.get("/dataset")
def dataset(
    _user=Depends(require_viewer),
):
    """Return the bundled labeled dataset (provenance transparency)."""
    return {"size": len(classifier.DATASET), "items": [
        {"text": t, "label": "passed" if l == 1 else "failed"} for t, l in classifier.DATASET
    ]}

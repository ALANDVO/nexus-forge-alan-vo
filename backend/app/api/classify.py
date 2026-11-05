"""ML classifier inspection and evaluation endpoints (opt-in, advisory)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..api.auth import require_viewer
from ..core import classifier

router = APIRouter(prefix="/classify", tags=["classifier"])


class ClassifyRequest(BaseModel):
    text: str


class ClassifyResponse(BaseModel):
    label: str
    passed: bool
    confidence: float
    agreement: str


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

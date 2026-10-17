"""Task execution and result-query endpoints."""
from __future__ import annotations

import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..models.plan import Filter
from ..services.ledger import RunService, Services, get_services

router = APIRouter(tags=["tasks", "results"])

_RESULT_FIELDS = (
    "task_id", "plan_id", "plan_name", "title", "label", "confidence",
    "agreement", "exit_code", "duration_ms", "last_line", "head", "created_at",
)


class RunCommand(BaseModel):
    command: List[str] = Field(..., min_length=1, max_length=16)
    timeout: Optional[int] = Field(120, ge=1, le=300)


class OutcomeResponse(BaseModel):
    task_id: str
    plan_id: str
    label: str
    passed: bool
    confidence: float
    agreement: str
    exit_code: Optional[int] = None
    duration_ms: int
    last_line: str
    head: str
    created_at: Optional[str] = None


class ResultRowResponse(BaseModel):
    task_id: str
    plan_id: str
    plan_name: str
    title: str
    label: str
    confidence: float
    agreement: str
    exit_code: Optional[int] = None
    duration_ms: int
    last_line: str
    head: str
    created_at: str


class PagedResults(BaseModel):
    items: List[ResultRowResponse]
    total: int
    limit: int
    offset: int


@router.post("/tasks/{task_id}/run", response_model=OutcomeResponse, status_code=status.HTTP_200_OK)
def run_task(task_id: str, body: RunCommand, services: Services = Depends(get_services)):
    svc = RunService(services.storage)
    try:
        outcome = svc.run(task_id=task_id, command=body.command, actor="api", timeout=body.timeout)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _outcome_response(outcome)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, services: Services = Depends(get_services)):
    task = services.storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return {"id": task.id, "title": task.title, "body": task.body,
            "status": task.status.value, "order": task.order}


@router.get("/tasks/{task_id}/result", response_model=OutcomeResponse)
def get_result(task_id: str, services: Services = Depends(get_services)):
    outcome = services.storage.outcomes_for_task(task_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"no outcome recorded: {task_id}")
    return _outcome_response(outcome)


@router.get("/results", response_model=PagedResults)
def list_results(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    plan_id: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    services: Services = Depends(get_services),
):
    f = Filter(plan_id=plan_id, label=label, q=q, limit=limit, offset=offset)
    rows, total = services.storage.list_outcomes(f)
    items = [ResultRowResponse(**{k: getattr(r, k) for k in _RESULT_FIELDS}) for r in rows]
    return PagedResults(items=items, total=total, limit=limit, offset=offset)


@router.get("/results/export", response_class=PlainTextResponse)
def export_results(
    plan_id: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
    services: Services = Depends(get_services),
):
    rows, _total = services.storage.list_outcomes(
        Filter(plan_id=plan_id, label=label, q=None, limit=100000, offset=0)
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(_RESULT_FIELDS))
    for r in rows:
        writer.writerow([getattr(r, k) for k in _RESULT_FIELDS])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


def _outcome_response(outcome):
    return OutcomeResponse(
        task_id=outcome.task_id, plan_id=outcome.plan_id, label=outcome.label,
        passed=outcome.passed, confidence=outcome.confidence, agreement=outcome.agreement,
        exit_code=outcome.exit_code, duration_ms=outcome.duration_ms,
        last_line=outcome.last_line, head=outcome.head, created_at=outcome.created_at,
    )
"""Plan lifecycle endpoints: create/import, list, get, tasks."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..services.ledger import PlanService, Services, get_services

router = APIRouter(prefix="/plans", tags=["plans"])


class PlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1, max_length=100000)
    import_url: Optional[str] = None  # future: remote plan import source (not fetched here)


class PlanResponse(BaseModel):
    id: str
    name: str
    status: str
    task_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    body: str
    status: str
    order: int


class PlanDetailResponse(PlanResponse):
    text: str
    tasks: list[TaskResponse] = []


class PagedPlans(BaseModel):
    items: list[PlanResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreate, services: Services = Depends(get_services)):
    svc = PlanService(services.storage)
    plan = svc.create(name=body.name, text=body.text, actor="api")
    return _plan_response(plan)


@router.get("", response_model=PagedPlans)
def list_plans(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    name: Optional[str] = Query(None),
    services: Services = Depends(get_services),
):
    rows = services.storage.list_plans(limit=limit, offset=offset, name=name)
    total = services.storage.count_plans()
    return PagedPlans(
        items=[_plan_response(p) for p in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{plan_id}", response_model=PlanDetailResponse)
def get_plan(plan_id: str, services: Services = Depends(get_services)):
    plan = services.storage.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan not found: {plan_id}")
    return PlanDetailResponse(
        id=plan.id, name=plan.name, status=plan.status.value, task_count=plan.task_count,
        created_at=plan.created_at, updated_at=plan.updated_at, text=plan.text,
        tasks=[TaskResponse(id=t.id, title=t.title, body=t.body, status=t.status.value, order=t.order)
               for t in plan.tasks],
    )


def _plan_response(plan):
    return PlanResponse(
        id=plan.id, name=plan.name, status=plan.status.value, task_count=plan.task_count,
        created_at=plan.created_at, updated_at=plan.updated_at,
    )
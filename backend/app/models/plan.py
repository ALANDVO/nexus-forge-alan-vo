"""Domain models and API schemas for plans, tasks and outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class Task:
    id: str
    title: str
    body: str = ""
    status: TaskStatus = TaskStatus.PENDING
    order: int = 0


@dataclass
class Plan:
    id: str
    name: str
    text: str
    status: PlanStatus = PlanStatus.DRAFT
    task_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tasks: list[Task] = field(default_factory=list)


@dataclass
class Outcome:
    task_id: str = ""
    plan_id: str = ""
    passed: bool = False
    label: str = "failed"
    confidence: float = 0.0
    agreement: str = "n/a"
    exit_code: Optional[int] = None
    duration_ms: int = 0
    last_line: str = ""
    head: str = ""
    created_at: Optional[str] = None


@dataclass
class ResultRow:
    """A result with joined plan/task context for listing/export."""

    task_id: str
    plan_id: str
    plan_name: str
    title: str
    label: str
    confidence: float
    agreement: str
    exit_code: Optional[int]
    duration_ms: int
    last_line: str
    head: str
    created_at: str


@dataclass
class Filter:
    plan_id: Optional[str] = None
    label: Optional[str] = None
    q: Optional[str] = None
    limit: int = 25
    offset: int = 0
    order: str = "created_at_desc"
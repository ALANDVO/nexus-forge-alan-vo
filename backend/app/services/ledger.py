"""High-level services: plan creation, task execution, result querying."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Request

from ..core.classifier import classify_outcome
from ..core.parsing import parse_tasks
from .storage import Storage
from ..models.plan import Outcome, Plan, PlanStatus, Task, TaskStatus


@dataclass
class Services:
    storage: Storage


def get_services(request: Request) -> Services:
    """FastAPI dependency: services bound to the application storage."""
    return Services(request.app.state.storage)


def _new_plan_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


class PlanService:
    """Creates plans and decomposes them into ordered tasks."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def create(self, name: str, text: str, actor: str = "api") -> Plan:
        tasks = parse_tasks(text)
        plan = Plan(id=_new_plan_id(), name=name, text=text, status=PlanStatus.DRAFT,
                    tasks=tasks, task_count=len(tasks))
        return self.storage.create_plan(plan, actor=actor)


class RunService:
    """Executes a single task against an operator-supplied, bounded command."""

    def __init__(self, storage: Storage, run_timeout_seconds: int = 120,
                 max_run_timeout_seconds: int = 300):
        self.storage = storage
        self.run_timeout_seconds = run_timeout_seconds
        self.max_run_timeout_seconds = max_run_timeout_seconds

    def run(self, task_id: str, command: List[str], actor: str = "api",
            timeout: Optional[int] = None) -> Outcome:
        from ..models.plan import Outcome as _Outcome  # noqa: F401

        if not command or not command[0]:
            raise ValueError("command must be a non-empty list")
        ttl = min(timeout or self.run_timeout_seconds, self.max_run_timeout_seconds)
        task = self.storage.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        self.storage.update_task_status(task_id, TaskStatus.RUNNING)

        start = datetime.now(timezone.utc)
        try:
            resolved = self._resolve_command(command)
            proc = subprocess.run(
                resolved, capture_output=True, text=True, timeout=ttl, check=False,
            )
            combined = f"{proc.stdout or ''}{('\n' + proc.stderr) if proc.stderr else ''}"
            exit_code: Optional[int] = proc.returncode
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout if isinstance(exc.stdout, str) else ""
            err = exc.stderr if isinstance(exc.stderr, str) else ""
            combined = f"{out}{('\n' + err) if err else ''}"
            outcome = self._failed(task_id, "timeout", None, combined, start)
            return self._finish(task, outcome, actor)
        except FileNotFoundError:
            outcome = self._failed(task_id, "command-not-found", None, "", start)
            return self._finish(task, outcome, actor)

        last_line, head = _split_lines(combined)
        label, passed, confidence, agreement = classify_outcome(
            exit_code, combined, last_line, head
        )
        outcome = Outcome(task_id=task_id, passed=passed, label=label, confidence=confidence,
                          agreement=agreement, exit_code=exit_code,
                          duration_ms=_duration_ms(start), last_line=last_line, head=head)
        return self._finish(task, outcome, actor)

    def _failed(self, task_id, agreement, exit_code, combined, start) -> Outcome:
        last_line, head = _split_lines(combined)
        return Outcome(task_id=task_id, passed=False, label="failed", confidence=1.0,
                       agreement=agreement, exit_code=exit_code, duration_ms=_duration_ms(start),
                       last_line=last_line or agreement, head=head or "error")

    def _finish(self, task, outcome: Outcome, actor: str) -> Outcome:
        status = TaskStatus.PASSED if outcome.passed else TaskStatus.FAILED
        self.storage.update_task_status(task.id, status)
        outcome.plan_id = self._plan_id(task)
        return self.storage.add_outcome(outcome, actor=actor)

    def _plan_id(self, task: Task) -> str:
        row = self.storage.get_task_with_plan(task.id)
        return row[1] if row else ""

    @staticmethod
    def _resolve_command(command: List[str]) -> List[str]:
        import os
        import shutil

        if shutil.which(command[0]) or os.path.isabs(command[0]):
            return command
        return command


def _split_lines(text: str) -> tuple[str, str]:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    head = lines[0] if lines else ""
    return last, head


def _duration_ms(start: datetime) -> int:
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
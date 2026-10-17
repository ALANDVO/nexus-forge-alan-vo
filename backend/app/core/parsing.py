"""Deterministic plan parsing: markdown plans -> ordered task lists.

Addresses the monolithic-plan inefficiency reported in issue #512 by decomposing
a single plan document into discrete, addressable tasks (the per-task "step files"
the user asked for, materialized as stable IDs).
"""
from __future__ import annotations

import re

from ..models.plan import Task, TaskStatus

_TASK_RE = re.compile(r"^-{1,3}\s*\[(?P<state>\s|x|X)\]\s+(?P<title>.*)$")
_NUMBER_RE = re.compile(r"^(?P<n>\d{1,3})[.)]\s+(?P<title>.*)$")
_HEADING_RE = re.compile(
    r"^#{1,6}\s+(?:task\s+)?(?P<n>\d{1,3})[.):\-]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)


def _slug(index: int, title: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{index:04d}-{safe[:80]}" if safe else f"{index:04d}-untitled"


def _drain_body(lines: list[str], index: int, stops: tuple[re.Pattern, ...]) -> tuple[str, int]:
    """Collect body lines until a stop pattern is hit or EOF."""
    body: list[str] = []
    j = index
    while j < len(lines):
        if any(r.match(lines[j]) for r in stops):
            break
        j += 1
    # body is the slice between index and j, trimmed of trailing blank lines
    body = lines[index:j]
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body).strip(), j


def parse_tasks(text: str) -> list[Task]:
    """Parse markdown ``text`` into ordered :class:`Task` objects.

    Supports (first match wins): GitHub task lists (``- [ ]``/``- [x]``),
    ``## Task N: title`` headings, then numbered steps. Empty/None input
    yields no tasks.
    """
    if not text or not text.strip():
        return []
    lines = text.splitlines()

    tasks = _parse_task_list(lines)
    if tasks:
        return tasks
    tasks = _parse_headings(lines)
    if tasks:
        return tasks
    return _parse_numbered(lines)


def _parse_task_list(lines: list[str]) -> list[Task]:
    tasks: list[Task] = []
    i = 0
    while i < len(lines):
        m = _TASK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        state = m.group("state").strip().lower()
        title = m.group("title").strip()
        body, next_i = _drain_body(lines, i + 1, (_TASK_RE,))
        status = TaskStatus.PASSED if state == "x" else TaskStatus.PENDING
        tasks.append(
            Task(id=_slug(len(tasks), title), title=title, body=body, status=status, order=len(tasks))
        )
        i = next_i
    return tasks


def _parse_headings(lines: list[str]) -> list[Task]:
    tasks: list[Task] = []
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i])
        if not m:
            i += 1
            continue
        title = m.group("title").strip()
        body, next_i = _drain_body(lines, i + 1, (_HEADING_RE,))
        tasks.append(
            Task(id=_slug(len(tasks), title), title=title, body=body, order=len(tasks))
        )
        i = next_i
    return tasks


def _parse_numbered(lines: list[str]) -> list[Task]:
    tasks: list[Task] = []
    i = 0
    while i < len(lines):
        m = _NUMBER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        title = m.group("title").strip()
        body, next_i = _drain_body(lines, i + 1, (_NUMBER_RE,))
        tasks.append(
            Task(id=_slug(len(tasks), title), title=title, body=body, order=len(tasks))
        )
        i = next_i
    return tasks
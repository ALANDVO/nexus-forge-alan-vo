from __future__ import annotations

from app.core.parsing import parse_tasks
from app.models.plan import TaskStatus


def test_empty_and_none_yield_no_tasks():
    assert parse_tasks("") == []
    assert parse_tasks("   \n\n  ") == []
    assert parse_tasks(None) == []  # type: ignore[arg-type]


def test_task_list_parses_into_ordered_tasks_with_status():
    text = "- [ ] first task\nbody line one\n  indented body\n- [x] done task\n"
    tasks = parse_tasks(text)
    assert len(tasks) == 2
    assert tasks[0].title == "first task"
    assert tasks[0].status == TaskStatus.PENDING
    assert tasks[0].order == 0
    assert tasks[0].body == "body line one\n  indented body"
    assert tasks[1].title == "done task"
    assert tasks[1].status == TaskStatus.PASSED
    assert tasks[1].order == 1
    assert tasks[0].id != tasks[1].id


def test_heading_style_decomposes_plan():
    text = "## Task 1: write parser\n\nSome detail.\n## Task 2: train model\n"
    tasks = parse_tasks(text)
    assert len(tasks) == 2
    assert tasks[0].title == "write parser"
    assert tasks[0].body == "Some detail."
    assert tasks[1].title == "train model"


def test_numbered_steps_fallback():
    text = "1. install deps\n2. run tests\n3. ship\n"
    tasks = parse_tasks(text)
    assert [t.title for t in tasks] == ["install deps", "run tests", "ship"]
    assert [t.order for t in tasks] == [0, 1, 2]


def test_task_list_takes_precedence_over_numbered():
    text = "1. not a task\n- [ ] real task\n"
    tasks = parse_tasks(text)
    assert len(tasks) == 1
    assert tasks[0].title == "real task"


def test_slug_is_stable_and_unique():
    text = "- [ ] do the thing\n- [ ] do the thing\n"
    tasks = parse_tasks(text)
    ids = [t.id for t in tasks]
    assert len(set(ids)) == 2
    assert tasks[0].id.startswith("0000-")
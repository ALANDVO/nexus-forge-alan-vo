from __future__ import annotations

from app.models.plan import Filter, Outcome, Plan, Task, TaskStatus
from app.services.storage import Storage

from app.models.plan import PlanStatus


def _storage(tmp_path) -> Storage:
    s = Storage(str(tmp_path / "s.sqlite"))
    s.init()
    return s


def _plan_with_tasks(tasks):
    return Plan(id="p1", name="demo", text="- [ ] t", status=PlanStatus.ACTIVE, tasks=tasks)


def test_create_plan_roundtrip_preserves_tasks(tmp_path):
    s = _storage(tmp_path)
    plan = _plan_with_tasks([Task(id="a", title="a", order=0), Task(id="b", title="b", order=1)])
    s.create_plan(plan, actor="tester")
    got = s.get_plan("p1")
    assert got is not None and len(got.tasks) == 2
    assert [t.title for t in got.tasks] == ["a", "b"]
    s.close()


def test_get_plan_missing_returns_none(tmp_path):
    s = _storage(tmp_path)
    assert s.get_plan("nope") is None
    s.close()


def test_list_plans_paginates(tmp_path):
    s = _storage(tmp_path)
    for i in range(3):
        s.create_plan(Plan(id=f"p{i}", name=f"plan{i}", text="- [ ] t", tasks=[]), actor="t")
    page = s.list_plans(limit=2, offset=0)
    assert len(page) == 2
    assert s.count_plans() == 3
    next_page = s.list_plans(limit=2, offset=2)
    assert len(next_page) == 1
    s.close()


def test_outcome_recorded_and_filtered(tmp_path):
    s = _storage(tmp_path)
    s.create_plan(_plan_with_tasks([Task(id="t1", title="t1", order=0),
                                    Task(id="t2", title="t2", order=1)]), actor="t")
    s.add_outcome(Outcome(task_id="t1", plan_id="p1", passed=True, label="passed",
                          confidence=0.99, agreement="match", exit_code=0, duration_ms=10,
                          last_line="# pass 1", head="# pass 1"))
    s.add_outcome(Outcome(task_id="t2", plan_id="p1", passed=False, label="failed",
                          confidence=1.0, agreement="match", exit_code=1, duration_ms=5,
                          last_line="# fail 1", head="# fail 1"))
    all_rows, total = s.list_outcomes(Filter(limit=100, offset=0))
    assert total == 2
    passed_rows, _ = s.list_outcomes(Filter(label="passed", limit=100, offset=0))
    assert len(passed_rows) == 1
    assert passed_rows[0].label == "passed"
    out = s.outcomes_for_task("t1")
    assert out is not None and out.passed is True
    s.close()


def test_update_task_status_and_audit(tmp_path):
    s = _storage(tmp_path)
    s.create_plan(_plan_with_tasks([Task(id="t", title="t", order=0)]), actor="t")
    s.update_task_status("t", TaskStatus.PASSED)
    row = s.conn.execute("SELECT status FROM tasks WHERE id=?", ("t",)).fetchone()
    assert row["status"] == "passed"
    audit = s.conn.execute(
        "SELECT action FROM audit WHERE action='plan.created'"
    ).fetchone()
    assert audit is not None
    s.close()


def test_full_text_search_filters_outcomes(tmp_path):
    s = _storage(tmp_path)
    s.create_plan(_plan_with_tasks([Task(id="t1", title="t1", order=0),
                                    Task(id="t2", title="t2", order=1)]), actor="t")
    s.add_outcome(Outcome(task_id="t1", plan_id="p1", passed=True, label="passed", confidence=0.9,
                          agreement="match", exit_code=0, duration_ms=3, last_line="# pass 1",
                          head="# pass 1"))
    s.add_outcome(Outcome(task_id="t2", plan_id="p1", passed=False, label="failed", confidence=1.0,
                          agreement="match", exit_code=1, duration_ms=2, last_line="failing",
                          head="Error: boom"))
    rows, total = s.list_outcomes(Filter(q="failing", limit=100, offset=0))
    assert total == 1
    assert rows[0].task_id == "t2"
    s.close()
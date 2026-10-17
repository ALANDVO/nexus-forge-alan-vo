from __future__ import annotations

import sys

from app.models.plan import TaskStatus
from app.services.ledger import PlanService, RunService
from app.services.storage import Storage

_PASS_CMD = ["sh", "-c", "printf '# pass 1\\n# fail 0\\n# duration_ms 10\\n'"]
_FAIL_CMD = ["sh", "-c", "printf '# pass 0\\n# fail 1\\n# duration_ms 5\\n'; exit 1"]


def _services(tmp_path):
    storage = Storage(str(tmp_path / "ledger.sqlite"))
    storage.init()
    return storage, PlanService(storage), RunService(storage)


def test_create_plan_decomposes_tasks(tmp_path):
    storage, plan_svc, _run = _services(tmp_path)
    plan = plan_svc.create("demo", "- [ ] a\n- [ ] b\n", actor="tester")
    fetched = storage.get_plan(plan.id)
    assert fetched is not None and len(fetched.tasks) == 2
    assert [t.title for t in fetched.tasks] == ["a", "b"]
    storage.close()


def test_run_records_meaningful_outcome_not_duration(tmp_path):
    # Regression for issue #2342: the ledger must record a pass/fail label,
    # not the trailing `# duration_ms ...` line, even when that line is last.
    storage, _plan, run = _services(tmp_path)
    plan = _plan.create("p", "- [ ] t\n")
    storage.close()  # ensure persisted for the run service's separate use
    storage, _p, run = _services(tmp_path)
    task_id = plan.tasks[0].id
    outcome = run.run(task_id=task_id, command=_PASS_CMD, actor="tester")
    assert outcome.passed is True
    assert outcome.label == "passed"
    assert outcome.last_line == "# duration_ms 10"  # the misleading line is preserved raw
    # but the *recorded* result label is meaningful, not the duration text
    stored = storage.outcomes_for_task(task_id)
    assert stored is not None and stored.label == "passed" and stored.passed is True
    storage.close()


def test_run_failure_records_failed(tmp_path):
    storage, _plan, run = _services(tmp_path)
    plan = _plan.create("p", "- [ ] t\n")
    outcome = run.run(task_id=plan.tasks[0].id, command=_FAIL_CMD, actor="tester")
    assert outcome.passed is False and outcome.label == "failed"
    assert outcome.exit_code == 1
    storage.close()


def test_run_missing_task_raises(tmp_path):
    _storage, _plan, run = _services(tmp_path)
    try:
        run.run(task_id="does-not-exist", command=["true"], actor="tester")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for missing task")
    _storage.close()


def test_run_rejects_empty_command(tmp_path):
    storage, _plan, run = _services(tmp_path)
    plan = _plan.create("p", "- [ ] t\n")
    try:
        run.run(task_id=plan.tasks[0].id, command=[], actor="tester")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty command")
    storage.close()


def test_classifier_conflict_path_via_outcome(tmp_path):
    # exit 1 with pass signals -> classifier-conflict, still failed (exit code wins)
    from app.core.classifier import classify_outcome

    label, passed, _conf, agreement = classify_outcome(
        1, "# pass 4\n# fail 0\n# duration_ms 52"
    )
    assert passed is False and label == "failed" and agreement == "classifier-conflict"
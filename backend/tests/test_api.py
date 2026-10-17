from __future__ import annotations

import pytest

_PASS_CMD = ["sh", "-c", "printf '# pass 1\\n# fail 0\\n# duration_ms 10\\n'"]


def test_create_plan_and_list(client):
    resp = client.post("/plans", json={"name": "demo", "text": "- [ ] a\n- [ ] b\n"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "demo"
    assert body["task_count"] == 2
    plan_id = body["id"]

    listing = client.get("/plans")
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == plan_id


def test_get_plan_returns_decomposed_tasks(client):
    created = client.post("/plans", json={"name": "p", "text": "- [ ] first\n- [ ] second\n"})
    plan_id = created.json()["id"]
    resp = client.get(f"/plans/{plan_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert len(detail["tasks"]) == 2
    assert detail["tasks"][0]["title"] == "first"


def test_run_task_end_to_end(client):
    created = client.post("/plans", json={"name": "p", "text": "- [ ] t\n"})
    plan_id = created.json()["id"]
    task_id = client.get(f"/plans/{plan_id}").json()["tasks"][0]["id"]
    ran = client.post(f"/tasks/{task_id}/run", json={"command": _PASS_CMD})
    assert ran.status_code == 200
    outcome = ran.json()
    assert outcome["label"] == "passed"
    assert outcome["passed"] is True
    stored = client.get(f"/tasks/{task_id}/result")
    assert stored.status_code == 200
    assert stored.json()["label"] == "passed"


def test_results_query_and_export(client):
    created = client.post("/plans", json={"name": "p", "text": "- [ ] t\n"})
    plan_id = created.json()["id"]
    task_id = client.get(f"/plans/{plan_id}").json()["tasks"][0]["id"]
    client.post(f"/tasks/{task_id}/run", json={"command": _PASS_CMD})

    res = client.get("/results")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["label"] == "passed"
    csv_resp = client.get("/results/export")
    assert csv_resp.status_code == 200
    body = csv_resp.text
    assert body.startswith("task_id,plan_id,plan_name,title,label,")
    assert "passed" in body


def test_classifier_endpoints(client):
    metrics = client.get("/classify/metrics")
    assert metrics.status_code == 200
    m = metrics.json()
    assert m["accuracy"] >= 0.9
    assert m["dataset_size"] >= 20

    cls = client.post("/classify", json={"text": "# pass 4\n# fail 0\n# duration_ms 52"})
    assert cls.status_code == 200
    assert cls.json()["label"] == "passed"


def test_validation_rejects_bad_plan(client):
    resp = client.post("/plans", json={"name": "", "text": "- [ ] x"})
    assert resp.status_code == 422


def test_404s(client):
    assert client.get("/plans/no-such").status_code == 404
    assert client.get("/tasks/no-such/result").status_code == 404
    assert client.post("/tasks/no-such/run", json={"command": ["true"]}).status_code == 404


def test_run_rejects_empty_command(client):
    resp = client.post("/tasks/x/run", json={"command": []})
    assert resp.status_code == 422 or resp.status_code == 400


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
# API reference

Base URL (dev): `http://127.0.0.1:8000`. All paths are relative to that base.
Responses are JSON unless noted. Pagination uses `?limit=` and `?offset=`.

## Health

`GET /health` → `{ "status": "ok", "version": "<v>", "db": "ok" }`

## Plans

`POST /plans` — create a plan from a markdown task list and decompose it into tasks.

Request:
```json
{ "name": "ship log", "text": "- [ ] parse plan\n- [x] classify outcomes\n- [ ] export" }
```
Response `201` → `{ "id", "name", "status", "task_count", "created_at", "updated_at" }`

`GET /plans?limit=25&offset=0&name=` → `{ "items": [PlanResponse], "total", "limit", "offset" }`

`GET /plans/{plan_id}` → `{ "id", "name", "status", "task_count", "text", "tasks": [Task], "created_at", "updated_at" }`

`Task` = `{ "id", "title", "body", "status", "order" }`.

## Tasks

`POST /tasks/{task_id}/run` — execute the task against an operator-supplied command.

Request:
```json
{ "command": ["sh", "-c", "printf '# pass 4\\n# fail 0\\n# duration_ms 1\\n'"], "timeout": 120 }
```
Response `200` → `OutcomeResponse`:
```json
{ "task_id", "plan_id", "label": "passed", "passed": true,
  "confidence": 1.0, "agreement": "match", "exit_code": 0,
  "duration_ms": 140, "last_line": "# duration_ms 1", "head": "# pass 4",
  "created_at": "<iso-8601 UTC>" }
```

`GET /tasks/{task_id}` → `{ "id", "title", "body", "status", "order" }`

`GET /tasks/{task_id}/result` → `OutcomeResponse`

## Outcomes / results ledger

`GET /results?limit=&offset=&plan_id=&label=&q=` → `{ "items": [ResultRow], "total", "limit", "offset" }`

`ResultRow` = `{ "task_id", "plan_id", "plan_name", "title", "label", "confidence",
"agreement", "exit_code", "duration_ms", "last_line", "head", "created_at" }`

`GET /results/export?plan_id=&label=` → CSV (text/csv).

## Classifier (AI/ML core)

`POST /classify` — classify a log without an authoritative exit code.

Request: `{ "text": "<runner log>" }` → `{ "label", "passed", "confidence", "agreement" }`

`GET /classify/metrics` → model evaluation metrics over the bundled dataset.

`GET /classify/dataset` → the labeled dataset (provenance transparency).

## Errors

Validation failures return `422`; missing resources return `404`; malformed
commands return `400`. Errors use FastAPI's standard `{"detail": "..."}` shape.
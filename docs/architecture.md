# Architecture

```
                HTTP clients
        ┌──────────────┬─────────────┐
        │  React UI    │  CLI/cURL   │
        │ (Vite, TS)   │             │
        └──────┬───────┴──────┬──────┘
               ▼              ▼
         /plans /tasks /results /classify
                 ┌──────────┐
                 │ FastAPI  │  (app.main:create_app)
                 │  :8000   │
                 └────┬─────┘
            ┌─────────┼──────────┐
            ▼         ▼         ▼
        PlansAPI   TasksAPI   ClassifyAPI
            │         │         │
            ▼         ▼         ▼
        ┌──────────────────────────┐
        │        SERVICES           │   ledger orchestration
        │  PlanService   RunService │
        └────────────┬─────────────┘
          ┌──────────┼─────────┐
          ▼          ▼          ▼
   storage(SQLite)  parsing    classifier(ML)
                    (markdown) (logit-reg SGD)

persistence: WAL SQLite at NEXUS_DB_PATH (default data/ledger.sqlite)
audit:       structured JSON-line logging + on-disk audit table
ML core:     deterministic, offline, no LLM key
auth:        planned milestone (OIDC/Keycloak) — see STATUS.md
```

## Layers

- **API** (`app/api/`): thin FastAPI routers. They depend on `Services` only via the
  `get_services` request dependency, so handlers stay testable.
- **Services** (`app/services/ledger.py`): orchestration. `PlanService` parses a plan
  into tasks; `RunService` executes one task and folds the result through the
  classifier; `ResultService`/storage answers ledger queries.
- **Storage** (`app/services/storage.py`): stdlib `sqlite3` (WAL), per-thread
  connections under a serializing lock. All mutations are committed; outcomes and
  tasks use `INSERT OR REPLACE` so a re-run updates in place.
- **Core** (`app/core/`): pure, deterministic. `parsing.py` decomposes markdown;
  `classifier.py` trains a logistic-regression classifier once (fixed seed) and
  caches it; `audit.py` emits structured audit events.
- **Frontend** (`frontend/src`): React + TS + Vite, typed client in `src/api.ts`,
  view router in `App.tsx`, domain components under `src/components`.

## Determinism

The parser and classifier are deterministic (fixed regex + fixed training seed).
`GET /classify/metrics` reports the metrics of the model trained on the bundled
hand-labeled dataset at startup.

## Security model (current checkpoint)

Round 1 omits authentication (planned milestone `auth-oidc`). Deployments must
place the API behind an OIDC gateway. See README "Security".
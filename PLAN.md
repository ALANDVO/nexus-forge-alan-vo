# Product development plan

Each round completes one feature or repair. Future items are planned, not implemented claims.

## Current round

auth-oidc

## Roadmap

### plan-ledger-core — Plan ledger with ML outcome classification

Status: done

Acceptance:
- Create a plan from markdown text and decompose it into ordered tasks via a deterministic parser
- Run a task command; capture stdout/exit code/duration; classify the outcome with the bundled from-scratch log classifier
- Persist plans, tasks, outcomes and audit rows in SQLite with UTC timestamps, pagination and filtering
- End-to-end HTTP workflow: POST /plans -> GET /plans/{id}/tasks -> POST /tasks/{id}/run -> GET /results (verified in tests)
- ML classifier evaluated on a bundled labeled dataset; accuracy/precision/recall exposed at GET /classify/metrics

Implementation: `backend/app/core/classifier.py`, `backend/app/core/parsing.py`, `backend/app/core/audit.py`, `backend/app/models/plan.py`, `backend/app/services/storage.py`, `backend/app/services/ledger.py`, `backend/app/api/plans.py`, `backend/app/api/tasks.py`, `backend/app/api/classify.py`, `backend/app/main.py`

Tests: `backend/tests/test_classifier.py`, `backend/tests/test_parsing.py`, `backend/tests/test_storage.py`, `backend/tests/test_ledger.py`, `backend/tests/test_api.py`

### frontend-dashboard — React dashboard for plans, tasks and results

Status: done

Acceptance:
- Typed API client derived from backend routes and response envelopes
- Plans dashboard with create and list, loading/error/empty states
- Task list with run and result view

Implementation: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/PlanDashboard.tsx`, `frontend/src/components/TaskList.tsx`, `frontend/src/components/ResultView.tsx`, `frontend/src/components/Loading.tsx`, `frontend/src/index.css`

Tests: `frontend/tests/api.test.ts`, `frontend/tests/dashboard.test.tsx`

### auth-oidc — Keycloak OIDC authorization-code login (state/nonce/PKCE) with role-based authorization

Status: planned

Acceptance:
- Unauthenticated requests rejected on all data endpoints
- OIDC callback exchange with state/nonce/PKCE; tokens validated (signature/issuer/audience)
- viewer/operator/admin roles enforced; explicit logout

### llm-adapters — Opt-in LLM providers (OpenAI-compatible, Anthropic, Gemini, Ollama) for advisory explanations

Status: planned

Acceptance:
- LLM_API_KEY only; server-side calls; bounded timeouts; redacted errors; advisory-only and grounded in records

### agent-teams — Agent-team orchestration primitives (#429)

Status: planned

Acceptance:
- Detect team context; scaffold teammate spawning and task assignment


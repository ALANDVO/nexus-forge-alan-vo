# Changelog

## 1.3.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## 1.2.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## 1.1.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

### Added (auth-oidc in_progress)
- OIDC authentication with Keycloak: authorization code flow with PKCE (state, nonce, code_verifier)
- Token validation via JWKS (RS256, signature/issuer/audience verification)
- Role-based access control (viewer, operator, admin) enforced on all data endpoints
- Auth endpoints: `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me`
- Auth middleware for automatic token extraction from Authorization header or cookies
- Optional auth dependencies for backward compatibility with existing tests (OIDC off = no auth required)
- All 36 existing backend tests and 7 frontend tests pass

## 1.0.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## [0.1.0] — initial checkpoint

### Added
- `backend/app` FastAPI application with a `create_app` factory and a single
  entrypoint used by both Docker and local `uvicorn` runs.
- Plan ledger: create/import a markdown plan, decompose it into ordered tasks
  (GitHub task-list / `## Task N` / numbered styles).
- Task execution: a bounded subprocess runner capturing stdout/exit code/
  duration; the runner's last non-blank line is preserved raw but the ledger
  records a meaningful pass/fail label (issue #2342 fix).
- From-scratch logistic-regression log classifier (no third-party ML
  dependency): trains once at startup on a hand-labeled dataset of real
  runner output and exposes `GET /classify/metrics` and `POST /classify`.
- SQLite persistence (WAL) for plans, tasks, outcomes and an audit log with
  UTC timestamps, pagination and filtering; CSV export of results.
- React + TypeScript + Vite dashboard with a typed API client: plan
  create/list/detail, task run with a demo command, and a results ledger view
  with filters and export.
- Dockerfiles (nonroot) for backend and frontend, `.dockerignore` files,
  `compose.yaml` (Keycloak under an `auth` profile), `.env.example`.
- CI workflow (tests, Docker builds, YAML/preflight validation).
- pytest + vitest suites (36 backend, 7 frontend) covering parsing, the
  classifier, persistence, the full HTTP create→run→query workflow and
  user-visible dashboard behavior.

### Known gaps (planned milestones)
- LLM provider adapters are not yet implemented; advisory explanation is a
  planned milestone.
- Agent-team orchestration primitives are not yet implemented.

---

Alan Vo · [alanvo.net](https://alanvo.net) · [X: @alanvoasi](https://x.com/alanvoasi)

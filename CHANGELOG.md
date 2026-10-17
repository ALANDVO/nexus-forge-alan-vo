# Changelog

## 1.0.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

All notable changes to this project are documented here. Dates use the author's
calendar; versions are allocated by the publisher controller.

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
- Authentication is not yet implemented; the API is unauthenticated and
  dev-only. See the README "Security" section and `STATUS.md`.
- LLM provider adapters are not yet implemented; advisory explanation is a
  planned milestone.
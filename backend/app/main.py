"""FastAPI application factory.

Docker and local commands use the same entrypoint:
``uvicorn app.main:app`` (module-level ``app = create_app()``).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import classify as classify_api
from .api import plans as plans_api
from .api import tasks as tasks_api
from .config import settings
from .services.storage import Storage


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Nexus Forge",
        description="Agentic skills framework: plan ledger with ML outcome classification.",
        version=settings.version,
    )

    app.state.storage = Storage(db_path=db_path or settings.db_path)
    app.state.storage.init()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # dev-only; auth proxy is intended for production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(plans_api.router)
    app.include_router(tasks_api.router)
    app.include_router(classify_api.router)

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "version": settings.version, "db": "ok"}

    @app.on_event("shutdown")
    def _shutdown():
        app.state.storage.close()

    return app


app = create_app()
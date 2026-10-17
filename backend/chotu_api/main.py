"""FastAPI app factory.

    uvicorn chotu_api.main:app --reload            # from backend/, sample data, demo robots
    CHOTU_STORE=sql DATABASE_URL=... uvicorn chotu_api.main:app
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import __version__, protocol
from .config import Settings
from .deps import require_key
from .repositories import build_repository
from .routers import history, live, robots
from .services.robot_link import build_link

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.repo = build_repository(settings)
        app.state.link = build_link(settings.robot_link, settings.sample_dir, settings.replay_speed)
        await app.state.link.start(app.state.repo.list_robots())
        try:
            yield
        finally:
            await app.state.link.stop()

    app = FastAPI(title="CHOTU fleet API", version=__version__, lifespan=lifespan,
                  description="Mission history, schedules, no-go zones, alerts and live telemetry for "
                              "CHOTU robots. Default mode serves sample data and replayed demo robots.")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])

    secured = [Depends(require_key)]
    app.include_router(robots.router, prefix="/api/v1", dependencies=secured)
    app.include_router(history.router, prefix="/api/v1", dependencies=secured)
    app.include_router(live.router)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"status": "ok", "version": __version__, "protocol": protocol.PROTOCOL_VERSION,
                "store": settings.store, "robot_link": settings.robot_link}

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(os.path.join(STATIC, "dashboard.html"))

    return app


app = create_app()

"""FastAPI 앱 — Dugout Game Server."""

from __future__ import annotations

import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from data.pipeline import DugoutDataPipeline
from .game_session import GameSessionManager
from .routes import router, set_session_manager
from .daily_routes import router as daily_router, init_daily
from .advisor_routes import router as advisor_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline = DugoutDataPipeline(season=2025)
    data = pipeline.load_all()
    mgr = GameSessionManager(data.teams, data.parks, data.league)
    set_session_manager(mgr)
    init_daily(data)
    yield


app = FastAPI(title="Dugout", description="AI Baseball Manager & Daily Predictions", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(daily_router)
app.include_router(advisor_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Static files — React 빌드 서빙
_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/assets", StaticFiles(directory=_web_dist / "assets"), name="assets")

    @app.get("/")
    def serve_spa():
        return FileResponse(_web_dist / "index.html")

    @app.get("/{path:path}")
    def serve_spa_fallback(path: str):
        file = _web_dist / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(_web_dist / "index.html")

"""Aplicação FastAPI — chatbot interno Rede Enleva."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes_admin import router as admin_router
from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_health import router as health_router
from backend.app.config import PROJECT_ROOT, get_settings
from backend.app.rag.ingest import ingest_knowledge, resolve_ingest_mode
from backend.app.rag.knowledge_watcher import run_knowledge_watcher
from backend.app.security.log_purge_scheduler import run_log_purge_scheduler
from backend.app.security.retention import purge_expired_logs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.log_path.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)

    # Rede de segurança: purge no startup (cobre restart do processo/container)
    purged = purge_expired_logs(settings.log_path, settings.log_retention_days)
    if purged:
        logger.info("Logs expirados removidos no startup: %s", purged)

    try:
        result = ingest_knowledge(settings=settings)
        logger.info("Ingestão inicial: %s", result.message)
    except Exception:
        logger.exception("Falha na ingestão inicial — API sobe sem índice")

    stop_event = asyncio.Event()
    purge_task = asyncio.create_task(
        run_log_purge_scheduler(
            log_path=settings.log_path,
            retention_days=settings.log_retention_days,
            hour_utc=settings.log_purge_hour_utc,
            stop_event=stop_event,
        ),
        name="log-purge-scheduler",
    )
    watch_task: asyncio.Task | None = None
    if settings.knowledge_watch_enabled:
        mode, _ = resolve_ingest_mode(settings)
        if mode == "files":
            watch_task = asyncio.create_task(
                run_knowledge_watcher(settings=settings, stop_event=stop_event),
                name="knowledge-watcher",
            )
        else:
            logger.info(
                "Watcher knowledge/ desligado — ingest via Postgres "
                "(use POST /admin/reindex após publicar no CMS)"
            )

    yield

    stop_event.set()
    tasks = [purge_task]
    if watch_task is not None:
        tasks.append(watch_task)
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()


app = FastAPI(
    title="Enleva Chatbot Interno",
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list or ["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(admin_router)

FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def root():
    demo = FRONTEND_DIR / "demo.html"
    if demo.exists():
        return FileResponse(demo)
    return {"status": "ok", "docs": "/docs"}


@app.get("/demo.html")
def demo_page():
    demo = FRONTEND_DIR / "demo.html"
    if not demo.exists():
        return {"error": "demo.html não encontrado"}
    return FileResponse(demo)

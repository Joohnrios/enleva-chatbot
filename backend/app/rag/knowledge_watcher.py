"""Watcher de knowledge/: reindex automático com debounce."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import Settings
from backend.app.rag.ingest import ingest_knowledge

logger = logging.getLogger(__name__)


def _is_knowledge_md(_change: object, path: str) -> bool:
    name = Path(path).name
    return name.endswith(".md") and not name.startswith("_")


async def run_knowledge_watcher(
    *,
    settings: Settings,
    stop_event: asyncio.Event,
) -> None:
    """Observa KNOWLEDGE_DIR e dispara ingest_knowledge após quietude (debounce)."""
    knowledge_path = settings.knowledge_path
    debounce_s = max(0.5, float(settings.knowledge_watch_debounce_seconds))
    knowledge_path.mkdir(parents=True, exist_ok=True)

    try:
        from watchfiles import awatch
    except ImportError:
        logger.warning(
            "watchfiles indisponível — watcher de knowledge/ desativado "
            "(use POST /admin/reindex)"
        )
        await stop_event.wait()
        return

    logger.info(
        "Watcher knowledge/ ativo em %s (debounce=%.1fs)",
        knowledge_path,
        debounce_s,
    )
    try:
        async for _changes in awatch(
            knowledge_path,
            watch_filter=_is_knowledge_md,
            debounce=int(debounce_s * 1000),
            stop_event=stop_event,
        ):
            if stop_event.is_set():
                break
            try:
                result = await asyncio.to_thread(ingest_knowledge, settings)
                logger.info("Reindex por watcher: %s", result.message)
            except Exception:
                logger.exception("Falha no reindex disparado pelo watcher")
    except asyncio.CancelledError:
        raise
    finally:
        logger.info("Watcher knowledge/ encerrado")

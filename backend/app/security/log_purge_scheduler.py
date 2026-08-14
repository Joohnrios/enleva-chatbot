"""Agendamento diário do purge de logs (UTC) dentro do processo da app."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.security.retention import purge_expired_logs

logger = logging.getLogger(__name__)


def seconds_until_next_purge(hour_utc: int, *, now: datetime | None = None) -> float:
    """Segundos até a próxima execução diária no horário UTC informado (0–23)."""
    hour = max(0, min(23, int(hour_utc)))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return max(1.0, (next_run - now).total_seconds())


async def run_log_purge_scheduler(
    *,
    log_path: Path,
    retention_days: int,
    hour_utc: int,
    stop_event: asyncio.Event,
) -> None:
    """Loop diário: espera até LOG_PURGE_HOUR_UTC e chama purge_expired_logs."""
    logger.info(
        "Agendador de purge de logs inicializado (diário às %02d:00 UTC; retenção=%sd)",
        hour_utc,
        retention_days,
    )
    while not stop_event.is_set():
        wait_s = seconds_until_next_purge(hour_utc)
        logger.debug("Próximo purge de logs em %.0fs", wait_s)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait_s)
            break
        except asyncio.TimeoutError:
            try:
                removed = purge_expired_logs(log_path, retention_days)
                logger.info(
                    "Purge agendado de logs concluído: %s arquivo(s) removido(s)",
                    removed,
                )
            except Exception:
                logger.exception("Falha no purge agendado de logs")

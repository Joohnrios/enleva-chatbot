"""Retenção e descarte seguro de logs de conversa (LGPD / POL RBD TI 001 §5.11)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


def ensure_log_dir(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)


def append_chat_log(
    log_dir: Path,
    *,
    session_id: str,
    message: str,
    reply: str,
    refused: bool,
    sources: list[str],
) -> Path:
    ensure_log_dir(log_dir)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = log_dir / f"chat-{day}.jsonl"
    record = {
        "id": str(uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "message": message,
        "reply": reply,
        "refused": refused,
        "sources": sources,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def purge_expired_logs(log_dir: Path, retention_days: int) -> int:
    """Remove arquivos de log mais antigos que retention_days. Retorna qtd removida."""
    if not log_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for path in log_dir.glob("chat-*.jsonl"):
        try:
            # Preferir data no nome; fallback para mtime
            date_part = path.stem.replace("chat-", "", 1)
            file_day = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            file_day = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if file_day.date() < cutoff.date():
            path.unlink(missing_ok=True)
            removed += 1
            logger.info("Log descartado por retenção: %s", path.name)
    return removed

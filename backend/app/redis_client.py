"""Cliente Redis opcional — se indisponível, callers usam fallback em memória."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from backend.app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> Any | None:
    """Retorna cliente redis ou None (URL vazia / conexão falhou)."""
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        logger.info("Redis conectado (%s)", url.split("@")[-1])
        return client
    except Exception:
        logger.warning(
            "Redis indisponível (%s) — rate limit/sessão em memória de processo",
            url.split("@")[-1] if url else "(vazio)",
            exc_info=True,
        )
        return None


def reset_redis_cache() -> None:
    get_redis.cache_clear()


def redis_available() -> bool:
    return get_redis() is not None

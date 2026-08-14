"""Engine SQLAlchemy sync — FastAPI só lê kb_domain / kb_document."""

from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def build_database_url(settings: Settings) -> str:
    user = settings.postgres_user
    password = settings.postgres_password
    host = settings.postgres_host
    port = settings.postgres_port
    db = settings.postgres_db
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def get_engine() -> Engine | None:
    settings = get_settings()
    if not settings.kb_sql_enabled:
        return None
    url = build_database_url(settings)
    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        logger.warning(
            "KB SQL indisponível (%s:%s/%s) — usando fallback local",
            settings.postgres_host,
            settings.postgres_port,
            settings.postgres_db,
            exc_info=True,
        )
        return None


def reset_engine_cache() -> None:
    get_engine.cache_clear()


def get_session() -> Session | None:
    engine = get_engine()
    if engine is None:
        return None
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()

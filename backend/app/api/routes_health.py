"""Rotas de health e config pública."""

from fastapi import APIRouter

from backend.app.config import get_settings
from backend.app.rag.store import get_store
from backend.app.schemas import HealthResponse, PublicConfigResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    try:
        store = get_store()
        count = store.count()
        index_ready = count > 0
    except Exception:
        count = 0
        index_ready = False
    return HealthResponse(
        status="ok",
        bot_name=settings.bot_name,
        llm_provider=settings.llm_provider,
        index_ready=index_ready,
        indexed_chunks=count,
    )


@router.get("/config/public", response_model=PublicConfigResponse)
def public_config() -> PublicConfigResponse:
    """Config para o widget. O token aqui é mitigação visível no browser, não auth real."""
    settings = get_settings()
    return PublicConfigResponse(
        bot_name=settings.bot_name,
        widget_api_token=settings.widget_api_token,
    )

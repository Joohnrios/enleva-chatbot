"""Endpoints administrativos (reindexação)."""

from fastapi import APIRouter, Header, HTTPException, Query

from backend.app.config import get_settings
from backend.app.rag.ingest import ingest_knowledge
from backend.app.schemas import ReindexResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reindex", response_model=ReindexResponse)
def reindex(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    full: bool = Query(
        default=False,
        description="Se true, apaga o índice e reindexa tudo (ignora file_hash).",
    ),
) -> ReindexResponse:
    settings = get_settings()
    expected = (settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN não configurado no servidor",
        )
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Token admin inválido")

    result = ingest_knowledge(settings=settings, full=full)
    return ReindexResponse(
        ok=True,
        indexed_files=result.indexed_files,
        indexed_chunks=result.indexed_chunks,
        unchanged_files=result.unchanged_files,
        removed_files=result.removed_files,
        skipped_files=result.skipped_files,
        message=result.message,
    )

"""Schemas Pydantic da API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None


class SourceRef(BaseModel):
    title: str
    source: str
    domain: str | None = None
    score: float | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[SourceRef] = Field(default_factory=list)
    refused: bool = False
    # out_of_scope | no_context | sensitive | None
    refusal_reason: str | None = None
    bot_name: str
    session_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    bot_name: str
    llm_provider: str
    index_ready: bool
    indexed_chunks: int = 0


class PublicConfigResponse(BaseModel):
    bot_name: str
    # Mitigação anti-scanner embutida no widget — NÃO é segredo forte / auth de sessão
    widget_api_token: str = ""


class ReindexResponse(BaseModel):
    ok: bool
    indexed_files: int
    indexed_chunks: int
    unchanged_files: int = 0
    removed_files: int = 0
    skipped_files: list[str] = Field(default_factory=list)
    message: str

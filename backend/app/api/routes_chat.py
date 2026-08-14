"""Endpoint de chat."""

from uuid import uuid4

from fastapi import APIRouter, Header, Request

from backend.app.config import get_settings
from backend.app.rag.orchestrator import answer_question
from backend.app.rag.session_memory import session_memory
from backend.app.schemas import ChatRequest, ChatResponse
from backend.app.security.rate_limit import enforce_chat_rate_limits
from backend.app.security.request_guards import (
    enforce_allowed_origin,
    enforce_widget_api_token,
)

router = APIRouter(tags=["chat"])

# TODO: autenticação real via token de sessão emitido pelo WordPress
# (substituir/complementar WIDGET_API_TOKEN + checagem de Origin).


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: Request,
    body: ChatRequest,
    x_widget_token: str | None = Header(default=None, alias="X-Widget-Token"),
) -> ChatResponse:
    settings = get_settings()

    # Camadas provisórias (mitigação pública) — falham fechado ANTES de RAG/LLM
    enforce_widget_api_token(settings=settings, x_widget_token=x_widget_token)
    enforce_allowed_origin(settings=settings, request=request)

    session_id = (body.session_id or "").strip() or str(uuid4())

    # Rate limit ANTES de qualquer chamada ao LLM / orquestração
    enforce_chat_rate_limits(
        request,
        session_id=session_id,
        bot_name=settings.bot_name,
        limit_ip=settings.rate_limit_chat,
        limit_session=settings.rate_limit_chat_session,
    )

    history = session_memory.get_history(
        session_id,
        ttl_minutes=settings.session_ttl_minutes,
        max_turns=settings.session_max_turns,
    )

    result = answer_question(
        body.message,
        session_id=session_id,
        history=history,
        persist_session=True,
    )
    return ChatResponse(
        reply=result.reply,
        sources=result.sources,
        refused=result.refused,
        refusal_reason=result.refusal_reason,
        bot_name=result.bot_name,
        session_id=result.session_id,
    )

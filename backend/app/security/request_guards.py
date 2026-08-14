"""Proteções provisórias do /chat (mitigação, NÃO autenticação real).

# TODO: autenticação real via token de sessão emitido pelo WordPress
# (token de curta duração para colaborador logado; validado aqui no backend).
# O desenho envolve o plugin/tema WP — ver conversa de arquitetura separada.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from backend.app.config import Settings


def enforce_widget_api_token(
    *,
    settings: Settings,
    x_widget_token: str | None,
) -> None:
    """Exige header ``X-Widget-Token`` igual a ``WIDGET_API_TOKEN`` do .env.

    Comparação via ``hmac.compare_digest`` (tempo constante).

    ATENÇÃO: o token é embutido no JS / em ``/config/public`` — visível no
    navegador. Isso só freia scanners/descoberta casual; **não** substitui
    autenticação de sessão real do colaborador.
    """
    expected = (settings.widget_api_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="WIDGET_API_TOKEN não configurado no servidor",
        )
    provided = (x_widget_token or "").strip()
    # compare_digest exige mesmo comprimento (senão TypeError → 500); mismatch = inválido
    if (
        not provided
        or len(provided) != len(expected)
        or not hmac.compare_digest(provided, expected)
    ):
        raise HTTPException(status_code=401, detail="Token de API inválido")


def _origin_allowed(candidate: str, allowed: list[str]) -> bool:
    cand = (candidate or "").strip()
    if not cand:
        return False
    for origin in allowed:
        if cand == origin or cand.startswith(origin.rstrip("/") + "/"):
            return True
    return False


def enforce_allowed_origin(*, settings: Settings, request: Request) -> None:
    """Exige Origin ou Referer alinhado a ALLOWED_ORIGINS (fallback: CORS_ORIGINS).

    Contornável forjando headers — barreira adicional, não autenticação.
    """
    allowed = settings.allowed_origin_list
    if not allowed:
        raise HTTPException(
            status_code=401,
            detail="Nenhuma origem permitida configurada (ALLOWED_ORIGINS/CORS_ORIGINS)",
        )

    origin = (request.headers.get("origin") or "").strip()
    if origin and origin in allowed:
        return

    referer = (request.headers.get("referer") or "").strip()
    if referer and _origin_allowed(referer, allowed):
        return

    raise HTTPException(
        status_code=401,
        detail="Origem da requisição não permitida",
    )

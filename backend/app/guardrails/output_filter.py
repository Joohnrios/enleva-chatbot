"""Filtro de saída para bloquear dados sensíveis acidentais."""

from __future__ import annotations

import re

from backend.app.guardrails.prompts import refusal_sensitive

CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
SALARY_RE = re.compile(
    r"(?i)(sal[aá]rio|remunera[cç][aã]o|contracheque|hollerith).{0,40}"
    r"(R\$\s*)?\d{1,3}(\.\d{3})*(,\d{2})?"
)
HEALTH_RE = re.compile(
    r"(?i)\b(diagn[oó]stico|prontu[aá]rio|cid-?\d+|exame laboratorial|"
    r"resultado do exame|doen[cç]a de)\b"
)


def contains_sensitive(text: str) -> bool:
    if CPF_RE.search(text):
        return True
    if SALARY_RE.search(text):
        return True
    if HEALTH_RE.search(text):
        return True
    return False


def filter_output(text: str, bot_name: str) -> tuple[str, bool]:
    """Retorna (texto_seguro, blocked)."""
    if contains_sensitive(text):
        return refusal_sensitive(bot_name), True
    return text, False

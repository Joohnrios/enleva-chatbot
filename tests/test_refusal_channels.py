"""Testes de prompts de refusal e resolução de canal."""

from __future__ import annotations

from backend.app.guardrails.prompts import refusal_no_context


def test_refusal_no_context_generic():
    text = refusal_no_context("Assistente")
    assert "GLPI" in text
    assert "Atendimento ao Colaborador" in text


def test_refusal_no_context_with_channel():
    text = refusal_no_context(
        "Assistente",
        contact_channel="GLPI",
        domain_name="TI",
    )
    assert "GLPI" in text
    assert "TI" in text
    assert "Atendimento ao Colaborador" not in text


def test_refusal_channel_only():
    text = refusal_no_context("Assistente", contact_channel="GLPI")
    assert "GLPI" in text
    assert "Não encontrei" in text

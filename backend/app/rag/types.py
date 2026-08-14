"""Tipos compartilhados do vector store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    text: str
    title: str
    source: str
    domain: str
    classification: str
    score: float

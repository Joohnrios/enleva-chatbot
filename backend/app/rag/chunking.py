"""Chunking de Markdown por headings."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    text: str
    chunk_index: int


def chunk_markdown(text: str, max_chars: int = 1800, overlap: int = 200) -> list[TextChunk]:
    """Divide texto preferindo headings; fallback por janela deslizante."""
    text = text.strip()
    if not text:
        return []

    sections = _split_by_headings(text)
    chunks: list[TextChunk] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        content = buffer.strip()
        if content:
            chunks.append(TextChunk(text=content, chunk_index=len(chunks)))
        buffer = ""

    for section in sections:
        if len(section) <= max_chars:
            if buffer and len(buffer) + len(section) + 2 > max_chars:
                flush()
            buffer = f"{buffer}\n\n{section}".strip() if buffer else section
            continue
        if buffer:
            flush()
        for piece in _window(section, max_chars, overlap):
            chunks.append(TextChunk(text=piece, chunk_index=len(chunks)))

    flush()
    return chunks


def _split_by_headings(text: str) -> list[str]:
    parts = re.split(r"(?m)(?=^#{1,3}\s+)", text)
    return [p.strip() for p in parts if p.strip()]


def _window(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [c for c in out if c]

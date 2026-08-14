# syntax=docker/dockerfile:1
# Multi-stage CPU-only image for Enleva chatbot (no CUDA).

ARG PYTHON_VERSION=3.12
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# ---------------------------------------------------------------------------
# Builder: deps + download embedding model (so runtime needs no HF download)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ARG EMBEDDING_MODEL
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache/sentence-transformers

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first — avoids pulling large CUDA wheels via sentence-transformers
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch

COPY requirements.txt .
RUN grep -vE '^(pytest|pytest-asyncio)([=<>]|$)' requirements.txt > /tmp/requirements.prod.txt \
    && pip install --no-cache-dir -r /tmp/requirements.prod.txt

# Bake embedding weights into the image (offline-friendly first start)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ---------------------------------------------------------------------------
# Runtime: slim, non-root, no build toolchain
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG EMBEDDING_MODEL
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/home/appuser/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/appuser/.cache/huggingface/sentence-transformers \
    EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    # Paths relative to /app (PROJECT_ROOT)
    KNOWLEDGE_DIR=./knowledge \
    CHROMA_DIR=./data/chroma \
    LOG_DIR=./data/logs

WORKDIR /app

# libgomp: required by CPU torch; curl: HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf-cache /home/appuser/.cache/huggingface

# Application code only (knowledge/data/.env come from compose mounts / env_file)
COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts

RUN mkdir -p /app/knowledge /app/data/chroma /app/data/logs \
    && chown -R appuser:appuser /app /home/appuser/.cache

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

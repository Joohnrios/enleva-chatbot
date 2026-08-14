"""Configuração via variáveis de ambiente (.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bot_name: str = Field(default="Assistente", alias="BOT_NAME")
    llm_provider: str = Field(default="anthropic", alias="LLM_PROVIDER")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-5", alias="ANTHROPIC_MODEL")
    anthropic_scope_model: str = Field(
        default="claude-haiku-4-5",
        alias="ANTHROPIC_SCOPE_MODEL",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")

    knowledge_dir: str = Field(default="./knowledge", alias="KNOWLEDGE_DIR")
    chroma_dir: str = Field(default="./data/chroma", alias="CHROMA_DIR")
    log_dir: str = Field(default="./data/logs", alias="LOG_DIR")
    log_retention_days: int = Field(default=90, alias="LOG_RETENTION_DAYS")
    log_purge_hour_utc: int = Field(default=3, alias="LOG_PURGE_HOUR_UTC")

    admin_token: str = Field(default="", alias="ADMIN_TOKEN")
    # Obrigatório em produção/piloto: mitigação anti-scanner (visível no JS — NÃO é auth real)
    widget_api_token: str = Field(default="", alias="WIDGET_API_TOKEN")
    cors_origins: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        alias="CORS_ORIGINS",
    )
    # Origens aceitas em Origin/Referer no /chat (vazio = usa CORS_ORIGINS)
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")

    # Defaults conservadores enquanto não há auth de sessão real (piloto controlado)
    rate_limit_chat: str = Field(default="10/minute", alias="RATE_LIMIT_CHAT")
    rate_limit_chat_session: str = Field(
        default="15/minute",
        alias="RATE_LIMIT_CHAT_SESSION",
    )

    retrieval_top_k: int = Field(default=4, alias="RETRIEVAL_TOP_K")
    retrieval_min_score: float = Field(default=0.35, alias="RETRIEVAL_MIN_SCORE")
    scope_local_min_score: float = Field(
        default=0.28,
        alias="SCOPE_LOCAL_MIN_SCORE",
    )
    scope_local_out_max: float = Field(
        default=0.18,
        alias="SCOPE_LOCAL_OUT_MAX",
    )
    session_max_turns: int = Field(default=6, alias="SESSION_MAX_TURNS")
    session_ttl_minutes: int = Field(default=60, alias="SESSION_TTL_MINUTES")
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL",
    )

    # Reindex automático ao editar ./knowledge (volume) — evita curl manual no piloto
    knowledge_watch_enabled: bool = Field(default=True, alias="KNOWLEDGE_WATCH_ENABLED")
    knowledge_watch_debounce_seconds: float = Field(
        default=2.0,
        alias="KNOWLEDGE_WATCH_DEBOUNCE_SECONDS",
    )
    # Força reset + reindex completo (startup/CLI); o endpoint aceita ?full=true
    ingest_force_full: bool = Field(default=False, alias="INGEST_FORCE_FULL")
    # auto | postgres | files — auto usa Document no Postgres se houver indexáveis
    ingest_source: str = Field(default="auto", alias="INGEST_SOURCE")
    # chroma (rollback/testes) | pgvector (padrão Compose)
    vector_store: str = Field(default="chroma", alias="VECTOR_STORE")
    embedding_dimensions: int = Field(default=384, alias="EMBEDDING_DIMENSIONS")

    # Leitura SQL das tabelas kb_* (Django dono do schema)
    kb_sql_enabled: bool = Field(default=True, alias="KB_SQL_ENABLED")
    postgres_db: str = Field(default="enleva_kb", alias="POSTGRES_DB")
    postgres_user: str = Field(default="enleva", alias="POSTGRES_USER")
    postgres_password: str = Field(default="enleva", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    # Redis: rate limit + sessão multi-turno compartilhados. Vazio = memória de processo.
    redis_url: str = Field(default="", alias="REDIS_URL")

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def knowledge_path(self) -> Path:
        return self.resolve_path(self.knowledge_dir)

    @property
    def chroma_path(self) -> Path:
        return self.resolve_path(self.chroma_dir)

    @property
    def log_path(self) -> Path:
        return self.resolve_path(self.log_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_origin_list(self) -> list[str]:
        raw = (self.allowed_origins or "").strip() or self.cors_origins
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

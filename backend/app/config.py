from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    # LLMs
    anthropic_api_key: str
    anthropic_model_sonnet: str = "claude-sonnet-4-6"
    anthropic_model_haiku: str = "claude-haiku-4-5-20251001"

    # Embeddings
    voyage_api_key: str
    voyage_model: str = "voyage-3-large"

    # Reranker
    cohere_api_key: str
    cohere_rerank_model: str = "rerank-3"

    # Parsing (optional)
    llama_cloud_api_key: str | None = None

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "clauseline"
    postgres_password: str = "clauseline"
    postgres_db: str = "clauseline"
    database_url: str = "postgresql+asyncpg://clauseline:clauseline@localhost:5432/clauseline"

    # Langfuse — optional in dev; tracing silently disabled if unset
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Retrieval knobs
    rrf_k: int = Field(default=60, ge=1)
    retrieval_top_k_dense: int = Field(default=20, ge=1)
    retrieval_top_k_sparse: int = Field(default=20, ge=1)
    rerank_top_k: int = Field(default=8, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

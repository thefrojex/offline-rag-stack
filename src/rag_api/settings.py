from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables only."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    llm_base_url: str = "http://ollama:11434/v1"
    llm_model: str = "llama3.2:3b"
    llm_api_key: str = "not-needed"
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=400, gt=0)
    llm_timeout_s: float = Field(default=180.0, gt=0)

    embed_base_url: str = "http://ollama:11434/v1"
    embed_model: str = "nomic-embed-text"
    embed_api_key: str = "not-needed"
    embed_dim: int = Field(default=768, gt=0)
    embed_batch_size: int = Field(default=16, gt=0)
    embed_document_prefix: str = "search_document: "
    embed_query_prefix: str = "search_query: "

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "documents"

    chunk_size: int = Field(default=900, gt=100)
    chunk_overlap: int = Field(default=120, ge=0)
    top_k: int = Field(default=4, gt=0, le=20)
    max_upload_mb: int = Field(default=25, gt=0)

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

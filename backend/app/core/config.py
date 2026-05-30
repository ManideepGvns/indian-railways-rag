from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # JWT — jwt_secret has a hardcoded fallback so JWT_SECRET need not be in .env.
    # Override via JWT_SECRET env var for production-grade security.
    jwt_secret: str = "ir-rag-default-secret-override-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # Database
    database_url: str = "sqlite:///./data/ir_rag.db"

    # Qdrant
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "ir_chunks"

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    # Chunking — used by the character splitter (fallback) and as overlap reference
    chunk_size: int = 400
    chunk_overlap: int = 50
    # Reduced from 8 → 5 to limit context size and cut LLM generation latency on CPU
    rag_top_k: int = 5

    # Agentic chunking (LLM-based boundary detection during ingestion)
    max_agentic_chunk_chars: int = 3000  # hard ceiling per chunk before forced split
    # Default timeout raised to 12 h — agentic chunking on CPU makes 1 LLM call per
    # paragraph boundary; an 800-page PDF can take several hours without a GPU.
    upload_timeout_secs: int = 43200

    # Seed admin
    admin_seed_username: str = "admin"
    admin_seed_password: str = "Admin@123"

    # Seed regular user
    user_seed_username: str = "user"
    user_seed_password: str = "User@123"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

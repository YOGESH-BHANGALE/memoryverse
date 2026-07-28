"""
Centralized configuration — reads .env and exposes typed settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    # ── Groq & HuggingFace ──────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    hf_embedding_model: str = "all-MiniLM-L6-v2"

    # ── ChromaDB ────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_prefix: str = "memoryverse"

    # ── Server ──────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ── Upload ──────────────────────────────────────────────────────────
    max_upload_size_mb: int = 50
    upload_dir: str = "./uploads"

    # ── LangChain ───────────────────────────────────────────────────────
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chroma_path(self) -> Path:
        p = Path(self.chroma_persist_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Singleton accessor for the settings object."""
    return Settings()

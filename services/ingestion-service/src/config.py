"""Ingestion Service configuration settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    service_name: str = "ingestion-service"
    service_port: int = 8002

    # ChromaDB configuration
    chromadb_host: str = "chromadb"
    chromadb_port: int = 8000

    # Downstream service URLs
    embedding_service_url: str = "http://embedding-service:8000"
    graph_service_url: str = "http://graph-service:8000"

    # File upload limits
    max_file_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: list[str] = [".txt", ".md", ".html", ".pdf"]

    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 30.0
    circuit_breaker_half_open_max_calls: int = 1

    # Retry settings
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_multiplier: float = 2.0
    retry_max_jitter: float = 0.5

    model_config = {"env_prefix": "INGESTION_"}

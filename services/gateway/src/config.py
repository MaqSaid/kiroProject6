"""Configuration settings for the API Gateway service."""

from __future__ import annotations

import os


class Settings:
    """Gateway configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.service_name: str = os.getenv("SERVICE_NAME", "gateway")
        self.query_service_url: str = os.getenv(
            "QUERY_SERVICE_URL", "http://query-service:8001"
        )
        self.ingestion_service_url: str = os.getenv(
            "INGESTION_SERVICE_URL", "http://ingestion-service:8002"
        )
        self.graph_service_url: str = os.getenv(
            "GRAPH_SERVICE_URL", "http://graph-service:8000"
        )
        self.embedding_service_url: str = os.getenv(
            "EMBEDDING_SERVICE_URL", "http://embedding-service:8000"
        )

        # API keys (comma-separated)
        api_keys_raw = os.getenv("API_KEYS", "dev-api-key-1,dev-api-key-2")
        self.api_keys: set[str] = {
            k.strip() for k in api_keys_raw.split(",") if k.strip()
        }

        # Rate limiting
        self.rate_limit_per_minute: int = int(
            os.getenv("RATE_LIMIT_PER_MINUTE", "60")
        )

        # CORS origins (comma-separated)
        cors_raw = os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        )
        self.cors_origins: list[str] = [
            o.strip() for o in cors_raw.split(",") if o.strip()
        ]

        # Proxy timeouts
        self.query_timeout: float = float(os.getenv("QUERY_TIMEOUT", "30.0"))
        self.ingestion_timeout: float = float(
            os.getenv("INGESTION_TIMEOUT", "60.0")
        )
        self.health_check_timeout: float = float(
            os.getenv("HEALTH_CHECK_TIMEOUT", "5.0")
        )

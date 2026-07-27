"""Configuration settings for the Query Service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Query Service configuration loaded from environment variables."""

    service_name: str = "query-service"
    service_port: int = 8001

    # Inter-service URLs
    embedding_service_url: str = "http://embedding-service:8000"
    graph_service_url: str = "http://graph-service:8000"

    # ChromaDB
    chromadb_host: str = "localhost"
    chromadb_port: int = 8000
    chromadb_collection: str = "legislation_chunks"

    # Circuit breaker settings
    circuit_failure_threshold: int = 5
    circuit_reset_timeout: float = 30.0

    # Timeouts
    embedding_timeout: float = 10.0
    graph_timeout: float = 5.0
    query_timeout: float = 30.0

    model_config = {"env_prefix": "QUERY_SERVICE_", "env_file": ".env"}

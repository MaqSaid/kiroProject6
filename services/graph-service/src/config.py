"""Graph Service configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Graph Service settings loaded from environment variables."""

    service_name: str = "graph-service"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"
    neo4j_max_pool_size: int = 50
    neo4j_connection_timeout: float = 5.0
    neo4j_query_timeout: float = 5.0

    model_config = {"env_prefix": "", "case_sensitive": False}

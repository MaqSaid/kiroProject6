"""Configuration settings for the Embedding Service."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Embedding Service configuration loaded from environment variables."""

    service_name: str = "embedding-service"
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv(
        "BEDROCK_MODEL_ID", "amazon.titan-embed-text-v2:0"
    )
    embedding_dimensions: int = 1024
    max_input_tokens: int = 8192
    host: str = "0.0.0.0"
    port: int = 8004

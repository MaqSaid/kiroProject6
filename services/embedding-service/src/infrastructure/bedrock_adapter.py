"""AWS Bedrock embedding adapter implementing EmbeddingPort."""

import json
from typing import Any

import boto3
import structlog
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from src.config import Settings

logger = structlog.get_logger(__name__)


class EmbeddingUnavailableError(Exception):
    """Raised when the Bedrock embedding service is unreachable."""

    pass


class BedrockEmbeddingAdapter:
    """Adapter for AWS Bedrock Titan Embed Text v2.

    Implements the EmbeddingPort protocol for generating text embeddings
    via the AWS Bedrock API.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None

    def initialize(self) -> None:
        """Create the Bedrock runtime client."""
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._settings.aws_region,
        )
        logger.info(
            "bedrock_adapter.initialized",
            region=self._settings.aws_region,
            model_id=self._settings.bedrock_model_id,
        )

    @property
    def client(self) -> Any:
        """Get the Bedrock runtime client."""
        if self._client is None:
            raise EmbeddingUnavailableError("Bedrock client not initialized")
        return self._client

    async def embed_text(self, text: str) -> tuple[list[float], int]:
        """Generate embedding for a single text via Bedrock.

        Args:
            text: Input text to embed.

        Returns:
            Tuple of (embedding vector, tokens used).

        Raises:
            EmbeddingUnavailableError: If Bedrock is unreachable.
        """
        try:
            body = json.dumps({
                "inputText": text,
                "dimensions": self._settings.embedding_dimensions,
                "normalize": True,
            })
            response = self._client.invoke_model(
                modelId=self._settings.bedrock_model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            vector = result["embedding"]
            tokens_used = result.get("inputTextTokenCount", self._estimate_tokens(text))
            return vector, tokens_used
        except (EndpointConnectionError, NoCredentialsError) as e:
            logger.error("bedrock.unavailable", error=str(e))
            raise EmbeddingUnavailableError(
                "AWS Bedrock embedding API is unreachable"
            ) from e
        except (BotoCoreError, ClientError) as e:
            logger.error("bedrock.call_failed", error=str(e))
            raise EmbeddingUnavailableError(
                "AWS Bedrock embedding API is unreachable"
            ) from e

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Generate embeddings for multiple texts via Bedrock.

        Bedrock Titan Embed does not support native batching, so this
        calls embed_text for each text sequentially.

        Args:
            texts: List of input texts to embed.

        Returns:
            Tuple of (list of embedding vectors, total tokens used).

        Raises:
            EmbeddingUnavailableError: If Bedrock is unreachable.
        """
        vectors: list[list[float]] = []
        total_tokens = 0
        for text in texts:
            vector, tokens = await self.embed_text(text)
            vectors.append(vector)
            total_tokens += tokens
        return vectors, total_tokens

    async def check_connectivity(self) -> bool:
        """Check Bedrock connectivity by embedding a test word.

        Returns:
            True if Bedrock responds successfully, False otherwise.
        """
        try:
            await self.embed_text("test")
            return True
        except EmbeddingUnavailableError:
            return False

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count as len(text) / 4 (rough approximation)."""
        return max(1, len(text) // 4)

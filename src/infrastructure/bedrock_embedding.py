"""Bedrock Titan Embeddings adapter for EmbeddingPort.

Uses Amazon Bedrock's Titan Text Embeddings V2 model to generate
dense vector representations of text. Stays entirely within AWS,
no OpenAI dependency needed.

Model: amazon.titan-embed-text-v2:0
Dimensions: 1024 (configurable: 256, 512, 1024)
Cost: ~$0.02 per 1M input tokens
"""

from __future__ import annotations

import json
import time
from typing import Any

import boto3
import structlog
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError

from src.ports.embedding import EmbeddingPort  # noqa: F401 — documents which port this implements

logger = structlog.get_logger(__name__)

# Default configuration
DEFAULT_MODEL_ID = "amazon.titan-embed-text-v2:0"
DEFAULT_REGION = "us-east-1"
DEFAULT_DIMENSIONS = 1024
DEFAULT_TIMEOUT = 10  # seconds
MAX_BATCH_SIZE = 25  # Process up to 25 texts per internal batch
MAX_INPUT_TOKENS = 8192  # Titan V2 max input length


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    def __init__(self, message: str, model_id: str = "", texts_count: int = 0) -> None:
        self.model_id = model_id
        self.texts_count = texts_count
        super().__init__(message)


class BedrockEmbeddingAdapter:
    """Amazon Bedrock Titan Embeddings adapter implementing EmbeddingPort.

    Generates dense embeddings using Titan Text Embeddings V2.
    Supports single and batch embedding with automatic chunking
    of large batches into API-compatible sizes.

    Usage:
        adapter = BedrockEmbeddingAdapter(region_name="us-east-1")
        vector = await adapter.embed_single("Hello world")
        vectors = await adapter.embed(["text1", "text2", "text3"])
    """

    def __init__(
        self,
        region_name: str = DEFAULT_REGION,
        model_id: str = DEFAULT_MODEL_ID,
        dimensions: int = DEFAULT_DIMENSIONS,
        timeout: int = DEFAULT_TIMEOUT,
        boto_session: Any | None = None,
    ) -> None:
        """Initialize the Bedrock embedding adapter.

        Args:
            region_name: AWS region for Bedrock API calls.
            model_id: Bedrock model identifier for embeddings.
            dimensions: Output vector dimensionality (256, 512, or 1024).
            timeout: Request timeout in seconds.
            boto_session: Optional custom boto3 session.
        """
        if dimensions not in (256, 512, 1024):
            raise ValueError(f"dimensions must be 256, 512, or 1024, got {dimensions}")

        self._model_id = model_id
        self._dimensions = dimensions
        self._timeout = timeout
        self._region_name = region_name

        boto_config = BotocoreConfig(
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=5,
            read_timeout=timeout,
        )

        if boto_session:
            self._client = boto_session.client(
                "bedrock-runtime",
                config=boto_config,
            )
        else:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=region_name,
                config=boto_config,
            )

        logger.info(
            "bedrock_embedding.initialized",
            model_id=self._model_id,
            region=region_name,
            dimensions=dimensions,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Automatically splits large batches into chunks of MAX_BATCH_SIZE
        and processes them sequentially.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.

        Raises:
            EmbeddingError: If the Bedrock API call fails.
        """
        if not texts:
            return []

        start_time = time.perf_counter()
        all_embeddings: list[list[float]] = []

        # Process in batches
        for batch_start in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[batch_start : batch_start + MAX_BATCH_SIZE]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "bedrock_embedding.embed.success",
            texts_count=len(texts),
            batches=((len(texts) - 1) // MAX_BATCH_SIZE) + 1,
            dimensions=self._dimensions,
            duration_ms=round(duration_ms, 2),
        )

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        Args:
            text: The text string to embed.

        Returns:
            A single embedding vector.

        Raises:
            EmbeddingError: If the Bedrock API call fails.
        """
        if not text or not text.strip():
            raise EmbeddingError(
                "Cannot embed empty text",
                model_id=self._model_id,
                texts_count=1,
            )

        start_time = time.perf_counter()

        embedding = await self._invoke_model(text)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "bedrock_embedding.embed_single.success",
            text_length=len(text),
            dimensions=self._dimensions,
            duration_ms=round(duration_ms, 2),
        )

        return embedding

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts (up to MAX_BATCH_SIZE).

        Titan V2 processes one text at a time via invoke_model.
        For production at scale, consider Bedrock batch inference.
        """
        embeddings: list[list[float]] = []

        for text in texts:
            if not text or not text.strip():
                # Return zero vector for empty text
                embeddings.append([0.0] * self._dimensions)
                continue

            embedding = await self._invoke_model(text)
            embeddings.append(embedding)

        return embeddings

    async def _invoke_model(self, text: str) -> list[float]:
        """Make a single embedding API call to Bedrock.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector.

        Raises:
            EmbeddingError: On API failure.
        """
        # Truncate if text exceeds model limit (~4 chars per token)
        max_chars = MAX_INPUT_TOKENS * 4
        if len(text) > max_chars:
            logger.warning(
                "bedrock_embedding.text_truncated",
                original_length=len(text),
                truncated_to=max_chars,
            )
            text = text[:max_chars]

        body = json.dumps({
            "inputText": text,
            "dimensions": self._dimensions,
            "normalize": True,
        })

        try:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )

            response_body = json.loads(response["body"].read())
            embedding: list[float] = response_body["embedding"]

            return embedding

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "bedrock_embedding.invoke_failed",
                error_code=error_code,
                error_message=error_msg,
                model_id=self._model_id,
                text_length=len(text),
            )

            raise EmbeddingError(
                f"Bedrock embedding failed: {error_code} - {error_msg}",
                model_id=self._model_id,
                texts_count=1,
            ) from e

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "bedrock_embedding.response_parse_failed",
                error=str(e),
                model_id=self._model_id,
            )

            raise EmbeddingError(
                f"Failed to parse Bedrock response: {e}",
                model_id=self._model_id,
                texts_count=1,
            ) from e

    @property
    def model_id(self) -> str:
        """Return the model ID being used."""
        return self._model_id

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self._dimensions

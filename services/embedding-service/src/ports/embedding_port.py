"""Protocol interface for embedding providers."""

from typing import Protocol


class EmbeddingPort(Protocol):
    """Port interface for embedding generation backends."""

    async def embed_text(self, text: str) -> tuple[list[float], int]:
        """Generate embedding vector for a single text.

        Args:
            text: Input text to embed.

        Returns:
            Tuple of (embedding vector, tokens used).

        Raises:
            EmbeddingUnavailableError: If the backend is unreachable.
        """
        ...

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.

        Returns:
            Tuple of (list of embedding vectors, total tokens used).

        Raises:
            EmbeddingUnavailableError: If the backend is unreachable.
        """
        ...

    async def check_connectivity(self) -> bool:
        """Check if the embedding backend is reachable.

        Returns:
            True if connected, False otherwise.
        """
        ...

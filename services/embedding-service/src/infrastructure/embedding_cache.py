"""SHA-256 hash-based in-memory embedding cache."""

import hashlib

import structlog

logger = structlog.get_logger(__name__)


class CacheEntry:
    """A cached embedding result."""

    __slots__ = ("vector", "tokens_used")

    def __init__(self, vector: list[float], tokens_used: int) -> None:
        self.vector = vector
        self.tokens_used = tokens_used


class EmbeddingCache:
    """In-memory embedding cache keyed by SHA-256 hash of input text.

    Provides O(1) lookup for previously computed embeddings to avoid
    redundant Bedrock API calls.
    """

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._initialized: bool = False

    def initialize(self) -> None:
        """Mark cache as initialized and ready for use."""
        self._initialized = True
        logger.info("embedding_cache.initialized")

    @property
    def is_initialized(self) -> bool:
        """Whether the cache has been initialized."""
        return self._initialized

    @staticmethod
    def compute_hash(text: str) -> str:
        """Compute SHA-256 hash of the input text.

        Args:
            text: Input text to hash.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> CacheEntry | None:
        """Look up a cached embedding by text content.

        Args:
            text: Input text to look up.

        Returns:
            CacheEntry if found, None otherwise.
        """
        key = self.compute_hash(text)
        return self._cache.get(key)

    def put(self, text: str, vector: list[float], tokens_used: int) -> None:
        """Store an embedding result in the cache.

        Args:
            text: Original input text (used to compute cache key).
            vector: Embedding vector to cache.
            tokens_used: Token count for the embedding.
        """
        key = self.compute_hash(text)
        self._cache[key] = CacheEntry(vector=vector, tokens_used=tokens_used)

    @property
    def size(self) -> int:
        """Number of entries in the cache."""
        return len(self._cache)

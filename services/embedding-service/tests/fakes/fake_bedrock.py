"""Fake Bedrock adapter for property testing.

Returns deterministic vectors based on SHA-256 hash of input text,
without calling AWS. Tracks call counts for cache verification.
"""

import hashlib
import struct


class FakeBedrockAdapter:
    """Deterministic Bedrock adapter that never calls AWS.

    Generates embedding vectors by hashing the input text with SHA-256,
    expanding the hash to fill the desired dimensionality. Tracks how
    many times embed_text and embed_batch are called.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self._dimensions = dimensions
        self.embed_text_call_count: int = 0
        self.embed_batch_call_count: int = 0
        self._texts_embedded: list[str] = []

    def _deterministic_vector(self, text: str) -> list[float]:
        """Generate a deterministic vector from text via SHA-256 expansion.

        Repeatedly hashes with incrementing salt to produce enough floats
        to fill the embedding dimensions.
        """
        vector: list[float] = []
        block = 0
        while len(vector) < self._dimensions:
            h = hashlib.sha256(f"{text}:{block}".encode("utf-8")).digest()
            # Each 32-byte hash gives us 8 floats (4 bytes each)
            for i in range(0, 32, 4):
                if len(vector) >= self._dimensions:
                    break
                # Unpack as unsigned int, normalize to [0, 1]
                val = struct.unpack(">I", h[i : i + 4])[0]
                vector.append(val / (2**32 - 1))
            block += 1
        return vector[: self._dimensions]

    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens as len(text) // 4, minimum 1."""
        return max(1, len(text) // 4)

    async def embed_text(self, text: str) -> tuple[list[float], int]:
        """Generate a deterministic embedding for a single text.

        Returns:
            Tuple of (vector, tokens_used).
        """
        self.embed_text_call_count += 1
        self._texts_embedded.append(text)
        vector = self._deterministic_vector(text)
        tokens_used = self._estimate_tokens(text)
        return vector, tokens_used

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Generate deterministic embeddings for multiple texts.

        Returns:
            Tuple of (list of vectors, total tokens_used).
        """
        self.embed_batch_call_count += 1
        vectors: list[list[float]] = []
        total_tokens = 0
        for text in texts:
            vector = self._deterministic_vector(text)
            tokens = self._estimate_tokens(text)
            vectors.append(vector)
            total_tokens += tokens
            self._texts_embedded.append(text)
        return vectors, total_tokens

    async def check_connectivity(self) -> bool:
        """Always returns True for testing."""
        return True

    def reset(self) -> None:
        """Reset call counts and tracked texts."""
        self.embed_text_call_count = 0
        self.embed_batch_call_count = 0
        self._texts_embedded = []

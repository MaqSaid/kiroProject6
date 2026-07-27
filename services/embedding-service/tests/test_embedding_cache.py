"""Unit tests for the SHA-256 embedding cache."""

import hashlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.embedding_cache import EmbeddingCache


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    def test_initialize_marks_cache_ready(self):
        cache = EmbeddingCache()
        assert not cache.is_initialized
        cache.initialize()
        assert cache.is_initialized

    def test_compute_hash_returns_sha256(self):
        text = "hello world"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert EmbeddingCache.compute_hash(text) == expected

    def test_get_returns_none_for_missing_key(self):
        cache = EmbeddingCache()
        cache.initialize()
        assert cache.get("not cached") is None

    def test_put_and_get_round_trip(self):
        cache = EmbeddingCache()
        cache.initialize()
        vector = [0.1, 0.2, 0.3]
        cache.put("test text", vector, 5)
        entry = cache.get("test text")
        assert entry is not None
        assert entry.vector == vector
        assert entry.tokens_used == 5

    def test_same_text_returns_same_entry(self):
        cache = EmbeddingCache()
        cache.initialize()
        cache.put("text A", [1.0, 2.0], 10)
        cache.put("text A", [3.0, 4.0], 20)
        entry = cache.get("text A")
        # Last put wins
        assert entry is not None
        assert entry.vector == [3.0, 4.0]
        assert entry.tokens_used == 20

    def test_different_texts_get_different_entries(self):
        cache = EmbeddingCache()
        cache.initialize()
        cache.put("text A", [1.0], 5)
        cache.put("text B", [2.0], 10)
        assert cache.get("text A").vector == [1.0]
        assert cache.get("text B").vector == [2.0]

    def test_size_tracks_entries(self):
        cache = EmbeddingCache()
        cache.initialize()
        assert cache.size == 0
        cache.put("a", [1.0], 1)
        assert cache.size == 1
        cache.put("b", [2.0], 2)
        assert cache.size == 2
        # Overwrite doesn't add new entry
        cache.put("a", [3.0], 3)
        assert cache.size == 2

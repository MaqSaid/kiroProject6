"""In-memory Cache stub for CachePort.

Simple dict-based cache with TTL support. Satisfies the port
interface so the pipeline works without Redis running.

Replace with RedisCache for production (persistence, distribution, eviction).
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from src.ports.cache import CachePort  # noqa: F401

logger = structlog.get_logger(__name__)


class InMemoryCache:
    """In-memory cache implementing CachePort.

    Stores key-value pairs with TTL expiration. Expired entries
    are cleaned up on access (lazy eviction).
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        logger.info("in_memory_cache.initialized")

    async def get(self, key: str) -> Any | None:
        """Get a value by key. Returns None if missing or expired."""
        entry = self._store.get(key)
        if entry is None:
            return None

        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a value with TTL (seconds)."""
        expires_at = time.time() + ttl
        self._store[key] = (value, expires_at)

    async def invalidate(self, pattern: str) -> None:
        """Invalidate keys matching a pattern (simple prefix match)."""
        prefix = pattern.rstrip("*")
        keys_to_remove = [k for k in self._store if k.startswith(prefix)]
        for key in keys_to_remove:
            del self._store[key]
        logger.info("in_memory_cache.invalidate", pattern=pattern, removed=len(keys_to_remove))

    @property
    def size(self) -> int:
        """Return number of entries (including expired)."""
        return len(self._store)

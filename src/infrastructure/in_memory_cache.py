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


class CacheError(Exception):
    """Raised when cache operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class InMemoryCache:
    """In-memory cache implementing CachePort.

    Stores key-value pairs with TTL expiration. Expired entries
    are cleaned up on access (lazy eviction).
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        logger.info("in_memory_cache.initialized")

    async def get(self, key: str) -> Any | None:
        """Get a value by key. Returns None if missing or expired.

        Args:
            key: The cache key to look up.

        Returns:
            The cached value, or None if not found or expired.
        """
        try:
            entry = self._store.get(key)
            if entry is None:
                logger.debug("in_memory_cache.get.miss", key=key)
                return None

            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                logger.debug("in_memory_cache.get.expired", key=key)
                return None

            logger.debug("in_memory_cache.get.hit", key=key)
            return value

        except Exception as e:
            logger.error(
                "in_memory_cache.get.failed",
                error=str(e),
                key=key,
            )
            raise CacheError(
                f"Failed to get cache key: {e}",
                operation="get",
            ) from e

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a value with TTL (seconds).

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds.
        """
        try:
            expires_at = time.time() + ttl
            self._store[key] = (value, expires_at)
            logger.debug("in_memory_cache.set.success", key=key, ttl=ttl)
        except Exception as e:
            logger.error(
                "in_memory_cache.set.failed",
                error=str(e),
                key=key,
            )
            raise CacheError(
                f"Failed to set cache key: {e}",
                operation="set",
            ) from e

    async def invalidate(self, pattern: str) -> None:
        """Invalidate keys matching a pattern (simple prefix match).

        Args:
            pattern: Glob-style pattern (only prefix* supported).
        """
        try:
            prefix = pattern.rstrip("*")
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._store[key]
            logger.info(
                "in_memory_cache.invalidate.success",
                pattern=pattern,
                removed=len(keys_to_remove),
            )
        except Exception as e:
            logger.error(
                "in_memory_cache.invalidate.failed",
                error=str(e),
                pattern=pattern,
            )
            raise CacheError(
                f"Failed to invalidate cache pattern: {e}",
                operation="invalidate",
            ) from e

    @property
    def size(self) -> int:
        """Return number of entries (including expired)."""
        return len(self._store)

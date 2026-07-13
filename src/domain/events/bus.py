from collections.abc import Callable
from typing import Any, Protocol


class EventBus(Protocol):
    async def publish(self, event: Any) -> None: ...
    def subscribe(self, event_type: type, handler: Callable) -> None: ...


class InMemoryEventBus:
    """In-memory event bus for local development and testing."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = {}
        self._published: list[Any] = []

    async def publish(self, event: Any) -> None:
        self._published.append(event)
        event_type = type(event)
        for handler in self._handlers.get(event_type, []):
            await handler(event)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    @property
    def published_events(self) -> list[Any]:
        """Access published events for testing."""
        return self._published.copy()

    def clear(self) -> None:
        """Clear all published events (for testing)."""
        self._published.clear()

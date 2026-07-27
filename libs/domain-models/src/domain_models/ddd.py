"""Domain-Driven Design base classes: DomainEvent, ValueObject, AggregateRoot."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """Base class for domain events.

    Domain events represent something that happened in the domain
    that domain experts care about.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique event ID")
    event_type: str = Field(..., min_length=1, description="Type name of the event")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the event occurred",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Event payload data"
    )


class ValueObject(BaseModel):
    """Base class for value objects.

    Value objects are immutable and identified by their attributes rather
    than an identity. They are equal if all their attributes are equal.
    """

    model_config = {"frozen": True}

    def __hash__(self) -> int:
        return hash(self.model_dump_json())


class DocumentId(ValueObject):
    """Value object representing a document identifier."""

    value: str = Field(..., min_length=1, description="Document identifier value")


class ChunkId(ValueObject):
    """Value object representing a chunk identifier."""

    value: str = Field(..., min_length=1, description="Chunk identifier value")


class EntityId(ValueObject):
    """Value object representing an entity identifier."""

    value: str = Field(..., min_length=1, description="Entity identifier value")


class AggregateRoot(BaseModel):
    """Base class for aggregate roots.

    Aggregate roots are the entry point for accessing a cluster of
    domain objects. They ensure consistency boundaries and emit domain events.
    """

    id: str = Field(..., min_length=1, description="Aggregate root identifier")
    version: int = Field(default=0, ge=0, description="Optimistic concurrency version")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )
    _domain_events: list[DomainEvent] = []

    def model_post_init(self, __context: Any) -> None:
        """Initialize the domain events list after model creation."""
        object.__setattr__(self, "_domain_events", [])

    def add_event(self, event: DomainEvent) -> None:
        """Register a domain event to be dispatched."""
        self._domain_events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """Collect and clear all pending domain events."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

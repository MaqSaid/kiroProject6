"""Shared domain models for the Legislation RAG Platform.

This package provides Pydantic v2 models, enums, and DDD base classes
shared across all microservices.
"""

from domain_models.enums import (
    ChunkingStrategy,
    CircuitState,
    LegalEntityType,
    LegalRelationshipType,
)
from domain_models.core import ExtractedEntity, ExtractedRelationship, ScoredChunk
from domain_models.api_models import (
    AgentAskRequest,
    AgentAskResponse,
    CitationResponse,
    ConfidenceScoreResponse,
    ErrorResponse,
    FallbackInfoResponse,
    SourceChunkResponse,
)
from domain_models.interservice import (
    EmbedBatchRequest,
    EmbedBatchResponse,
    EmbedRequest,
    EmbedResponse,
    StoreEntitiesRequest,
    StoreRelationshipsRequest,
    TraverseRequest,
    TraverseResponse,
)
from domain_models.health import AggregatedHealthResponse, ServiceHealthStatus
from domain_models.ddd import (
    AggregateRoot,
    ChunkId,
    DocumentId,
    DomainEvent,
    EntityId,
    ValueObject,
)

__all__ = [
    # Enums
    "ChunkingStrategy",
    "CircuitState",
    "LegalEntityType",
    "LegalRelationshipType",
    # Core models
    "ExtractedEntity",
    "ExtractedRelationship",
    "ScoredChunk",
    # API models
    "AgentAskRequest",
    "AgentAskResponse",
    "CitationResponse",
    "ConfidenceScoreResponse",
    "ErrorResponse",
    "FallbackInfoResponse",
    "SourceChunkResponse",
    # Inter-service models
    "EmbedBatchRequest",
    "EmbedBatchResponse",
    "EmbedRequest",
    "EmbedResponse",
    "StoreEntitiesRequest",
    "StoreRelationshipsRequest",
    "TraverseRequest",
    "TraverseResponse",
    # Health models
    "AggregatedHealthResponse",
    "ServiceHealthStatus",
    # DDD base classes
    "AggregateRoot",
    "ChunkId",
    "DocumentId",
    "DomainEvent",
    "EntityId",
    "ValueObject",
]

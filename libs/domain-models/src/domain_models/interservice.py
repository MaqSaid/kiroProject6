"""Inter-service communication models for service-to-service requests."""

from pydantic import BaseModel, Field

from domain_models.core import ExtractedEntity, ExtractedRelationship, ScoredChunk


class EmbedRequest(BaseModel):
    """Request body for POST /embed (single text embedding)."""

    text: str = Field(..., min_length=1, description="Text to embed")


class EmbedResponse(BaseModel):
    """Response body for POST /embed."""

    vector: list[float] = Field(..., description="Embedding vector")
    tokens_used: int = Field(..., ge=0, description="Number of tokens consumed")


class EmbedBatchRequest(BaseModel):
    """Request body for POST /embed/batch (batch text embedding)."""

    texts: list[str] = Field(..., min_length=1, description="List of texts to embed")


class EmbedBatchResponse(BaseModel):
    """Response body for POST /embed/batch."""

    vectors: list[list[float]] = Field(..., description="List of embedding vectors")
    tokens_used: int = Field(..., ge=0, description="Total tokens consumed across all texts")


class TraverseRequest(BaseModel):
    """Request body for POST /traverse (graph traversal)."""

    query: str = Field(..., min_length=1, description="Query text for traversal matching")
    max_hops: int = Field(
        default=2, ge=1, le=5, description="Maximum traversal depth (capped at 5)"
    )


class TraverseResponse(BaseModel):
    """Response body for POST /traverse."""

    results: list[ScoredChunk] = Field(
        default_factory=list, description="Scored chunks from graph traversal"
    )


class StoreEntitiesRequest(BaseModel):
    """Request body for POST /entities (batch entity storage)."""

    entities: list[ExtractedEntity] = Field(
        ..., min_length=1, description="List of entities to store"
    )


class StoreRelationshipsRequest(BaseModel):
    """Request body for POST /relationships (batch relationship storage)."""

    relationships: list[ExtractedRelationship] = Field(
        ..., min_length=1, description="List of relationships to store"
    )

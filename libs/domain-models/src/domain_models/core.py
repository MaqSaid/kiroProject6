"""Core domain models for entities, relationships, and scored chunks."""

from typing import Any

from pydantic import BaseModel, Field

from domain_models.enums import LegalEntityType, LegalRelationshipType


class ExtractedEntity(BaseModel):
    """A legal entity extracted from a legislative document."""

    id: str = Field(..., min_length=1, description="Unique identifier for the entity")
    name: str = Field(..., min_length=1, description="Name of the legal entity")
    entity_type: LegalEntityType = Field(..., description="Type of legal entity")
    description: str = Field(default="", description="Description of the entity")
    source_chunk_id: str = Field(
        ..., min_length=1, description="ID of the chunk this entity was extracted from"
    )
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Additional properties for the entity"
    )


class ExtractedRelationship(BaseModel):
    """A relationship between two legal entities."""

    id: str = Field(..., min_length=1, description="Unique identifier for the relationship")
    source_entity_id: str = Field(
        ..., min_length=1, description="ID of the source entity"
    )
    target_entity_id: str = Field(
        ..., min_length=1, description="ID of the target entity"
    )
    relationship_type: LegalRelationshipType = Field(
        ..., description="Type of relationship"
    )
    description: str = Field(default="", description="Description of the relationship")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Additional properties for the relationship"
    )


class ScoredChunk(BaseModel):
    """A document chunk with a relevance score from retrieval."""

    chunk_id: str = Field(..., min_length=1, description="Unique identifier for the chunk")
    document_id: str = Field(..., min_length=1, description="ID of the source document")
    text: str = Field(..., description="Text content of the chunk")
    section_heading: str = Field(..., description="Section heading for the chunk")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score between 0 and 1")
    retrieval_method: str = Field(
        ..., min_length=1, description="Method used to retrieve this chunk"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata for the chunk"
    )

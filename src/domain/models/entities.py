from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models.enums import ChunkingStrategy, DocumentFormat, RRFWeights

# --- Documents ---


class RawDocument(BaseModel):
    id: UUID
    filename: str
    format: DocumentFormat
    content: bytes
    uploaded_by: str
    uploaded_at: datetime
    size_bytes: int


class Section(BaseModel):
    heading: str
    level: int
    start_offset: int
    end_offset: int
    page_number: int | None = None


class DocumentMetadata(BaseModel):
    source_path: str
    format: DocumentFormat
    page_count: int | None = None
    ingested_at: datetime
    chunk_count: int = 0


class NormalizedDocument(BaseModel):
    id: UUID
    source_document_id: UUID
    plaintext: str
    sections: list[Section]
    metadata: DocumentMetadata


# --- Chunks ---


class Chunk(BaseModel):
    id: UUID
    document_id: UUID
    index: int
    text: str
    section_heading: str
    strategy: ChunkingStrategy
    char_count: int
    metadata: dict[str, Any] = {}


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float
    retrieval_method: str  # "dense", "sparse", "graph", "fused"


class EmbeddingRecord(BaseModel):
    chunk_id: UUID
    document_id: UUID
    vector: list[float]
    metadata: dict[str, Any]


# --- Knowledge Graph ---


class ExtractedEntity(BaseModel):
    id: UUID
    name: str
    entity_type: str  # e.g., "Person", "Concept", "Technology"
    description: str
    source_chunk_id: UUID
    properties: dict[str, Any] = {}


class ExtractedRelationship(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str  # e.g., "USES", "DEPENDS_ON", "PART_OF"
    description: str
    source_chunk_id: UUID
    properties: dict[str, Any] = {}


# --- Query & Response ---


class Query(BaseModel):
    text: str
    top_k: int = 10
    rrf_weights: RRFWeights | None = None
    include_graph: bool = True


class Citation(BaseModel):
    index: int  # [1], [2], etc.
    chunk_id: UUID
    claim: str
    source_text: str
    verified: bool = False
    verification_score: float | None = None


class ConfidenceScore(BaseModel):
    retrieval_confidence: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    answer_completeness: float = Field(ge=0.0, le=1.0)
    composite: float = Field(ge=0.0, le=1.0)


class FallbackInfo(BaseModel):
    found: list[str]
    not_found: list[str]
    suggested_documents: list[str]


class GenerationResult(BaseModel):
    answer: str
    citations: list[Citation]
    context_chunks: list[ScoredChunk]
    confidence: ConfidenceScore
    is_fallback: bool = False
    fallback_info: FallbackInfo | None = None

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models.entities import Citation, ConfidenceScore
from src.domain.models.enums import DocumentFormat, RRFWeights


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    rrf_weights: RRFWeights | None = None
    include_graph: bool = True


class SourceReference(BaseModel):
    document_id: UUID
    document_name: str
    section: str
    relevance_score: float
    retrieval_method: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: ConfidenceScore
    sources: list[SourceReference]
    correlation_id: str
    degraded_mode: list[str] = []


class IngestResponse(BaseModel):
    document_id: UUID
    filename: str
    format: DocumentFormat
    chunk_count: int
    entity_count: int
    status: str
    correlation_id: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    correlation_id: str
    details: dict[str, Any] = {}


class DocumentListItem(BaseModel):
    document_id: UUID
    filename: str
    format: DocumentFormat
    chunk_count: int
    ingested_at: str
    size_bytes: int

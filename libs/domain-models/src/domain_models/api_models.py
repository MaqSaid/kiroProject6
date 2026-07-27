"""API request and response models for the platform endpoints."""

from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    """Request body for POST /v1/agents/ask."""

    query: str = Field(..., min_length=1, max_length=2000, description="User query text")


class CitationResponse(BaseModel):
    """A single citation in an agent response."""

    index: int = Field(..., ge=0, description="Citation index number")
    source_reference: str = Field(..., description="Source document and section reference")
    claim: str = Field(..., description="The claim being cited")
    verification_status: str = Field(
        ..., description="Status of citation verification (e.g., 'verified', 'unsupported')"
    )


class ConfidenceScoreResponse(BaseModel):
    """Confidence score breakdown for an agent response."""

    retrieval_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in retrieval quality"
    )
    citation_coverage: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of cited to total factual statements"
    )
    answer_completeness: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of addressed to total query concepts"
    )
    composite: float = Field(
        ..., ge=0.0, le=1.0, description="Weighted composite confidence score"
    )


class SourceChunkResponse(BaseModel):
    """A source chunk included in the response."""

    chunk_id: str = Field(..., min_length=1, description="Unique chunk identifier")
    document_id: str = Field(..., min_length=1, description="Source document identifier")
    text: str = Field(..., description="Text content of the chunk")
    section_heading: str = Field(..., description="Section heading of the chunk")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    retrieval_method: str = Field(..., min_length=1, description="Retrieval method used")


class FallbackInfoResponse(BaseModel):
    """Information provided in a fallback response."""

    found_topics: list[str] = Field(
        default_factory=list, description="Topics with partial information found"
    )
    not_found_topics: list[str] = Field(
        default_factory=list, description="Topics with no information found"
    )
    suggested_documents: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 suggested documents for manual consultation",
    )


class AgentAskResponse(BaseModel):
    """Response body for POST /v1/agents/ask."""

    answer: str = Field(..., description="Generated answer text")
    citations: list[CitationResponse] = Field(
        default_factory=list, description="List of citations supporting the answer"
    )
    confidence_scores: ConfidenceScoreResponse = Field(
        ..., description="Confidence score breakdown"
    )
    source_chunks: list[SourceChunkResponse] = Field(
        default_factory=list, description="Retrieved source chunks"
    )
    is_fallback: bool = Field(
        ..., description="Whether this is a fallback response due to low confidence"
    )
    fallback_info: FallbackInfoResponse | None = Field(
        default=None, description="Fallback details when is_fallback is True"
    )


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error_code: str = Field(..., min_length=1, description="Machine-readable error code")
    message: str = Field(..., min_length=1, description="Human-readable error message")
    correlation_id: str = Field(
        ..., min_length=1, description="Correlation ID for distributed tracing"
    )

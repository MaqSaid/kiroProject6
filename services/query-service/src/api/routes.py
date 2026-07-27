"""API routes for the Query Service."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from domain_models.api_models import (
    AgentAskRequest,
    AgentAskResponse,
    ErrorResponse,
)
from src.api.dependencies import get_correlation_id, get_orchestrator
from src.orchestrator import RAGOrchestrator

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/agents/ask", response_model=AgentAskResponse)
async def agents_ask(
    body: AgentAskRequest,
    orchestrator: RAGOrchestrator = Depends(get_orchestrator),
    correlation_id: str = Depends(get_correlation_id),
) -> AgentAskResponse | JSONResponse:
    """Full agent-orchestrated query pipeline.

    Routes the query through the RAGOrchestrator which coordinates
    Retrieval, Generation, Citation Verification, and Evaluation agents.
    Must respond within 30 seconds.
    """
    try:
        response = await orchestrator.ask(body.query, correlation_id)
        return response
    except Exception as exc:
        logger.error(
            "agents_ask.failed",
            error=str(exc),
            error_type=type(exc).__name__,
            correlation_id=correlation_id,
        )
        error = ErrorResponse(
            error_code=f"{type(exc).__name__.upper()}_FAILURE",
            message=str(exc) or "Agent pipeline failed",
            correlation_id=correlation_id,
        )
        return JSONResponse(content=error.model_dump(), status_code=500)


@router.post("/ask", response_model=AgentAskResponse)
async def direct_ask(
    body: AgentAskRequest,
    orchestrator: RAGOrchestrator = Depends(get_orchestrator),
    correlation_id: str = Depends(get_correlation_id),
) -> AgentAskResponse | JSONResponse:
    """Direct retrieval-only query (no full agent pipeline).

    Simpler path: just retrieval + basic answer generation.
    Retained for backward compatibility.
    """
    try:
        response = await orchestrator.direct_ask(body.query, correlation_id)
        return response
    except Exception as exc:
        logger.error(
            "direct_ask.failed",
            error=str(exc),
            error_type=type(exc).__name__,
            correlation_id=correlation_id,
        )
        error = ErrorResponse(
            error_code=f"{type(exc).__name__.upper()}_FAILURE",
            message=str(exc) or "Query processing failed",
            correlation_id=correlation_id,
        )
        return JSONResponse(content=error.model_dump(), status_code=500)

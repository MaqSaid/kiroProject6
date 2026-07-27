"""FastAPI dependency injection for the Query Service."""

import uuid

from fastapi import Request

from src.orchestrator import RAGOrchestrator


def get_orchestrator(request: Request) -> RAGOrchestrator:
    """Retrieve the RAGOrchestrator from app state."""
    return request.app.state.orchestrator


def get_correlation_id(request: Request) -> str:
    """Extract correlation ID from request state or generate a new one."""
    return getattr(request.state, "correlation_id", str(uuid.uuid4()))

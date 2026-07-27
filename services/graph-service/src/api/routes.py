"""Graph Service REST API routes."""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from domain_models import (
    StoreEntitiesRequest,
    StoreRelationshipsRequest,
    TraverseRequest,
    TraverseResponse,
)
from src.infrastructure.neo4j_adapter import GraphStoreUnavailableError

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["graph"])


@router.post("/entities", status_code=201)
async def store_entities(body: StoreEntitiesRequest, request: Request) -> dict:
    """Batch store entities using MERGE by entity id."""
    graph_store = request.app.state.graph_store
    try:
        stored_count = await graph_store.store_entities(body.entities)
        return {"stored_count": stored_count}
    except GraphStoreUnavailableError as e:
        logger.error("store_entities.neo4j_unavailable", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "NEO4J_UNAVAILABLE",
                "message": str(e),
                "correlation_id": request.headers.get("x-correlation-id", "unknown"),
            },
        )


@router.post("/relationships", status_code=201)
async def store_relationships(body: StoreRelationshipsRequest, request: Request) -> dict:
    """Batch store relationships with MERGE by relationship id."""
    graph_store = request.app.state.graph_store
    try:
        stored_count, skipped_count = await graph_store.store_relationships(
            body.relationships
        )
        return {"stored_count": stored_count, "skipped_count": skipped_count}
    except GraphStoreUnavailableError as e:
        logger.error("store_relationships.neo4j_unavailable", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "NEO4J_UNAVAILABLE",
                "message": str(e),
                "correlation_id": request.headers.get("x-correlation-id", "unknown"),
            },
        )


@router.post("/traverse")
async def traverse_graph(body: TraverseRequest, request: Request) -> TraverseResponse:
    """Execute graph traversal query with variable-length paths."""
    graph_store = request.app.state.graph_store
    try:
        results = await graph_store.traverse(
            query=body.query, max_hops=body.max_hops
        )
        return TraverseResponse(results=results)
    except GraphStoreUnavailableError as e:
        logger.error("traverse.neo4j_unavailable", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "NEO4J_UNAVAILABLE",
                "message": str(e),
                "correlation_id": request.headers.get("x-correlation-id", "unknown"),
            },
        )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, request: Request) -> dict:
    """Delete all entities and relationships for a document."""
    graph_store = request.app.state.graph_store
    try:
        deleted_nodes, deleted_relationships = await graph_store.delete_by_document(
            document_id
        )
        return {
            "deleted_nodes": deleted_nodes,
            "deleted_relationships": deleted_relationships,
        }
    except GraphStoreUnavailableError as e:
        logger.error("delete_document.neo4j_unavailable", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "NEO4J_UNAVAILABLE",
                "message": str(e),
                "correlation_id": request.headers.get("x-correlation-id", "unknown"),
            },
        )

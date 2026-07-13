"""Core pipeline API routes: ask, ingest, documents, health."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Request, UploadFile

from src.api.models import AskRequest, ErrorResponse
from src.domain.models.entities import RawDocument
from src.domain.models.enums import ChunkingStrategy, DocumentFormat

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health", tags=["health"])
async def health():
    """Liveness probe."""
    return {"status": "healthy"}


@router.get("/ready", tags=["health"])
async def ready(request: Request):
    """Readiness probe."""
    checks = {
        "vector_store": request.app.state.vector_store.count >= 0,
        "sparse_index": request.app.state.sparse_index.count >= 0,
    }
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}


@router.post(
    "/v1/ask",
    response_model=dict[str, Any],
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["query"],
)
async def ask(request_body: AskRequest, request: Request):
    """Ask a question — hybrid search + reranking."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))

    # Security scan
    scan = request.app.state.security_service.scan_query(request_body.query)
    if not scan.passed:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "PROMPT_INJECTION_DETECTED",
                "message": scan.reason,
                "correlation_id": correlation_id,
            },
        )

    # Retrieve
    try:
        results = await request.app.state.retrieval_service.retrieve(
            query=request_body.query,
            top_k=request_body.top_k,
            rrf_weights=request_body.rrf_weights,
            include_graph=request_body.include_graph,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.error("api.ask.failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail={
            "error_code": "RETRIEVAL_ERROR",
            "message": str(e),
            "correlation_id": correlation_id,
        }) from e

    sources = [
        {
            "chunk_id": str(sc.chunk.id),
            "document_id": str(sc.chunk.document_id),
            "text": sc.chunk.text,
            "section": sc.chunk.section_heading,
            "score": round(sc.score, 4),
            "retrieval_method": sc.retrieval_method,
        }
        for sc in results
    ]

    # Generate answer with citations
    generation_service = request.app.state.generation_service
    try:
        gen_result = await generation_service.generate(
            query=request_body.query,
            chunks=results,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.warning("api.ask.generation_failed", error=str(e))
        return {
            "query": request_body.query,
            "answer": f"Retrieved {len(results)} chunks (generation unavailable).",
            "sources": sources,
            "source_count": len(sources),
            "correlation_id": correlation_id,
        }

    return {
        "query": request_body.query,
        "answer": gen_result.answer,
        "citations": [
            {
                "index": c.index,
                "claim": c.claim,
                "source_text": c.source_text[:200],
                "verified": c.verified,
            }
            for c in gen_result.citations
        ],
        "confidence": {
            "retrieval_confidence": gen_result.confidence.retrieval_confidence,
            "citation_coverage": gen_result.confidence.citation_coverage,
            "answer_completeness": gen_result.confidence.answer_completeness,
            "composite": gen_result.confidence.composite,
        },
        "sources": sources,
        "source_count": len(sources),
        "is_fallback": gen_result.is_fallback,
        "correlation_id": correlation_id,
    }


@router.post(
    "/v1/ingest",
    response_model=dict[str, Any],
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["ingestion"],
)
async def ingest(file: UploadFile, request: Request):
    """Ingest a document — normalize, chunk, index."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))

    if not file.filename:
        raise HTTPException(status_code=400, detail={
            "error_code": "MISSING_FILENAME",
            "message": "File must have a filename",
            "correlation_id": correlation_id,
        })

    # Determine format
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    format_map = {
        "txt": DocumentFormat.PLAINTEXT,
        "md": DocumentFormat.MARKDOWN,
        "html": DocumentFormat.HTML,
        "htm": DocumentFormat.HTML,
        "pdf": DocumentFormat.PDF,
    }
    doc_format = format_map.get(ext)
    if not doc_format:
        raise HTTPException(status_code=400, detail={
            "error_code": "UNSUPPORTED_FORMAT",
            "message": f"Unsupported extension: .{ext}. Supported: .txt, .md, .html, .pdf",
            "correlation_id": correlation_id,
        })

    content = await file.read()

    doc = RawDocument(
        id=uuid4(),
        filename=file.filename,
        format=doc_format,
        content=content,
        uploaded_by="api-user",
        uploaded_at=datetime.utcnow(),
        size_bytes=len(content),
    )

    try:
        result = await request.app.state.ingestion_service.ingest(
            doc, ChunkingStrategy.FIXED_SIZE, correlation_id
        )
    except Exception as e:
        logger.error("api.ingest.failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail={
            "error_code": "INGESTION_ERROR",
            "message": str(e),
            "correlation_id": correlation_id,
        }) from e

    return result


@router.get("/v1/documents", tags=["documents"])
async def list_documents(request: Request):
    """List ingested documents."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))

    try:
        docs = await request.app.state.document_store.list_documents()
        return {
            "documents": [
                {
                    "source_path": d.source_path,
                    "format": d.format.value,
                    "ingested_at": d.ingested_at.isoformat(),
                }
                for d in docs
            ],
            "total": len(docs),
            "correlation_id": correlation_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "error_code": "LIST_ERROR",
            "message": str(e),
            "correlation_id": correlation_id,
        }) from e

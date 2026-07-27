"""API routes for the Ingestion Service.

POST /v1/ingest - Upload and ingest a document
GET /v1/documents - List ingested documents
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import APIRouter, Request, UploadFile, File, Form, Response
from service_client import CircuitBreakerOpenError, MaxRetriesExceededError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["ingestion"])

# Maximum file size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".html", ".pdf"}


@dataclass
class DocumentRecord:
    """In-memory record of an ingested document."""

    document_id: str
    filename: str
    format: str
    ingestion_date: str
    chunks_produced: int
    chunking_strategy: str


# In-memory document store
_documents: dict[str, DocumentRecord] = {}


def _get_documents_store() -> dict[str, DocumentRecord]:
    """Return the in-memory documents store."""
    return _documents


@router.post("/ingest", status_code=201)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    chunking_strategy: str | None = Form(default=None),
) -> Any:
    """Upload and ingest a document.

    Accepts multipart file upload, validates format/size, chunks the document,
    generates embeddings via Embedding Service, stores vectors in ChromaDB + BM25,
    and stores entities via Graph Service.
    """
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))

    # --- Validate file extension ---
    filename = file.filename or "unknown"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        return Response(
            content=_error_json(
                "VALIDATION_ERROR",
                f"Unsupported file format '{ext}'. Allowed: .txt, .md, .html, .pdf",
                correlation_id,
            ),
            status_code=422,
            media_type="application/json",
        )

    # --- Read file content and validate size ---
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return Response(
            content=_error_json(
                "VALIDATION_ERROR",
                f"File size {len(content)} bytes exceeds maximum of {MAX_FILE_SIZE} bytes (50 MB)",
                correlation_id,
            ),
            status_code=422,
            media_type="application/json",
        )

    # --- Normalize text ---
    text = _normalize_text(content, ext)
    if not text.strip():
        return Response(
            content=_error_json(
                "VALIDATION_ERROR",
                "File content is empty after normalization",
                correlation_id,
            ),
            status_code=422,
            media_type="application/json",
        )

    # --- Select chunker and chunk document ---
    chunker_registry = request.app.state.chunker_registry
    document_id = f"doc-{uuid.uuid4().hex[:12]}"

    if chunking_strategy:
        try:
            chunker = chunker_registry.get_by_name(chunking_strategy)
        except ValueError as e:
            return Response(
                content=_error_json("VALIDATION_ERROR", str(e), correlation_id),
                status_code=422,
                media_type="application/json",
            )
        selected_strategy = chunking_strategy
    else:
        chunker = chunker_registry.auto_select(filename)
        selected_strategy = _determine_strategy_name(chunker_registry, chunker)

    # Create a simplified document for chunking
    from src.domain.processing.legal_hierarchical_chunker import (
        NormalizedDocument,
        Section,
    )

    doc = NormalizedDocument(
        id=uuid.uuid4(),
        source_document_id=uuid.UUID(document_id.replace("doc-", "").ljust(32, "0")),
        plaintext=text,
        sections=[
            Section(heading="", level=0, start_offset=0, end_offset=len(text))
        ],
        source_path=filename,
    )

    try:
        chunks = chunker.chunk(doc)
    except Exception as e:
        logger.error("chunking_failed", error=str(e), document_id=document_id)
        return Response(
            content=_error_json("INTERNAL_ERROR", "Document chunking failed", correlation_id),
            status_code=500,
            media_type="application/json",
        )

    chunk_texts = [chunk.text for chunk in chunks]
    chunk_ids = [str(chunk.id) for chunk in chunks]

    logger.info(
        "document_chunked",
        document_id=document_id,
        filename=filename,
        chunks_produced=len(chunks),
        strategy=selected_strategy,
    )

    # --- Call Embedding Service (critical) ---
    embedding_client = request.app.state.embedding_client
    try:
        embed_response = await embedding_client.post(
            "/embed/batch",
            correlation_id=correlation_id,
            json={"texts": chunk_texts},
        )
        if embed_response.status_code != 200:
            logger.error(
                "embedding_service_error",
                status_code=embed_response.status_code,
                document_id=document_id,
            )
            return Response(
                content=_error_json(
                    "DEPENDENCY_UNAVAILABLE",
                    "Embedding Service returned an error; document ingestion cannot complete",
                    correlation_id,
                ),
                status_code=503,
                media_type="application/json",
            )
        embed_data = embed_response.json()
        vectors = embed_data["vectors"]
    except (CircuitBreakerOpenError, MaxRetriesExceededError, Exception) as e:
        logger.error(
            "embedding_service_unavailable",
            error=str(e),
            document_id=document_id,
        )
        return Response(
            content=_error_json(
                "DEPENDENCY_UNAVAILABLE",
                "Embedding Service is unreachable; document ingestion cannot complete",
                correlation_id,
            ),
            status_code=503,
            media_type="application/json",
        )

    # --- Store vectors in ChromaDB ---
    chromadb_store = request.app.state.chromadb_store
    metadatas = [
        {
            "document_id": document_id,
            "filename": filename,
            "chunk_index": i,
            "section_heading": chunk.section_heading,
            "strategy": selected_strategy,
        }
        for i, chunk in enumerate(chunks)
    ]
    try:
        chromadb_store.store_vectors(
            ids=chunk_ids,
            vectors=vectors,
            documents=chunk_texts,
            metadatas=metadatas,
        )
    except Exception as e:
        logger.error("chromadb_store_failed", error=str(e), document_id=document_id)
        return Response(
            content=_error_json("INTERNAL_ERROR", "Failed to store vectors", correlation_id),
            status_code=500,
            media_type="application/json",
        )

    # --- Index in BM25 ---
    bm25_index = request.app.state.bm25_index
    try:
        bm25_index.add_documents(chunk_ids, chunk_texts)
    except Exception as e:
        logger.warning("bm25_index_failed", error=str(e), document_id=document_id)

    # --- Call Graph Service (non-critical, degraded mode on failure) ---
    graph_client = request.app.state.graph_client
    entities = _extract_entities(chunk_texts, chunk_ids, document_id)
    relationships = _extract_relationships(entities, document_id)

    graph_degraded = False
    if entities:
        try:
            await graph_client.post(
                "/entities",
                correlation_id=correlation_id,
                json={"entities": entities},
            )
            logger.info("entities_stored", count=len(entities), document_id=document_id)
        except (CircuitBreakerOpenError, MaxRetriesExceededError, Exception) as e:
            graph_degraded = True
            logger.warning(
                "graph_service_unavailable",
                error=str(e),
                document_id=document_id,
                message="Completing ingestion without graph storage (degraded mode)",
            )

    if relationships and not graph_degraded:
        try:
            await graph_client.post(
                "/relationships",
                correlation_id=correlation_id,
                json={"relationships": relationships},
            )
            logger.info("relationships_stored", count=len(relationships), document_id=document_id)
        except (CircuitBreakerOpenError, MaxRetriesExceededError, Exception) as e:
            logger.warning(
                "graph_service_relationships_unavailable",
                error=str(e),
                document_id=document_id,
                message="Completing ingestion without relationship storage (degraded mode)",
            )

    # --- Store document record ---
    now = datetime.now(timezone.utc).isoformat()
    record = DocumentRecord(
        document_id=document_id,
        filename=filename,
        format=ext.lstrip("."),
        ingestion_date=now,
        chunks_produced=len(chunks),
        chunking_strategy=selected_strategy,
    )
    _documents[document_id] = record

    logger.info(
        "document_ingested",
        document_id=document_id,
        filename=filename,
        chunks_produced=len(chunks),
        strategy=selected_strategy,
    )

    return {
        "document_id": document_id,
        "filename": filename,
        "chunks_produced": len(chunks),
        "chunking_strategy": selected_strategy,
    }


@router.get("/documents")
async def list_documents() -> dict[str, list[dict[str, Any]]]:
    """List all ingested documents sorted by ingestion_date descending."""
    docs = sorted(
        _documents.values(),
        key=lambda d: d.ingestion_date,
        reverse=True,
    )
    return {
        "documents": [
            {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "format": doc.format,
                "ingestion_date": doc.ingestion_date,
                "chunks_produced": doc.chunks_produced,
            }
            for doc in docs
        ]
    }


# --- Helper functions ---


def _error_json(error_code: str, message: str, correlation_id: str) -> str:
    """Create a JSON error response body."""
    import json

    return json.dumps({
        "error_code": error_code,
        "message": message,
        "correlation_id": correlation_id,
    })


def _normalize_text(content: bytes, ext: str) -> str:
    """Normalize file content to plaintext based on extension."""
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts)
        except Exception as e:
            logger.warning("pdf_extraction_failed", error=str(e))
            return content.decode("utf-8", errors="replace")
    elif ext == ".html":
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "lxml")
            return soup.get_text(separator="\n")
        except Exception:
            return content.decode("utf-8", errors="replace")
    else:
        # .txt and .md: decode as UTF-8
        return content.decode("utf-8", errors="replace")


def _determine_strategy_name(registry: Any, chunker: Any) -> str:
    """Determine the strategy name for a given chunker instance."""
    for strategy_info in registry.registered_strategies:
        name = strategy_info["name"]
        try:
            registered_chunker = registry.get_by_name(name)
            if registered_chunker is chunker:
                return name
        except ValueError:
            continue
    return "unknown"


def _extract_entities(
    chunk_texts: list[str], chunk_ids: list[str], document_id: str
) -> list[dict[str, Any]]:
    """Simplified entity extraction: extract capitalized multi-word phrases as entities.

    This is a basic implementation — in production, the Ingestion Agent would
    handle this with more sophisticated NLP.
    """
    entities: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # Pattern: 2+ capitalized words in sequence (e.g., "Transport Infrastructure Act")
    pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")

    for chunk_id, text in zip(chunk_ids, chunk_texts):
        matches = pattern.findall(text)
        for match in matches:
            name = match.strip()
            if name in seen_names or len(name) < 5:
                continue
            seen_names.add(name)
            entities.append({
                "id": f"ent-{uuid.uuid4().hex[:12]}",
                "name": name,
                "entity_type": "Act",
                "description": f"Entity extracted from document {document_id}",
                "source_chunk_id": chunk_id,
                "properties": {"document_id": document_id},
            })

    return entities


def _extract_relationships(
    entities: list[dict[str, Any]], document_id: str
) -> list[dict[str, Any]]:
    """Extract relationships between entities within the same document.

    This is a simplified implementation — in production, the Ingestion Agent
    would use NLP to detect cross-references (AMENDS, REFERENCES, etc.).
    Currently creates CONTAINS relationships between consecutive entities
    found in the same chunk, and REFERENCES between entities sharing keywords.
    """
    relationships: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Group entities by source_chunk_id
    entities_by_chunk: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        chunk_id = entity["source_chunk_id"]
        if chunk_id not in entities_by_chunk:
            entities_by_chunk[chunk_id] = []
        entities_by_chunk[chunk_id].append(entity)

    # Create CONTAINS relationships between entities in the same chunk
    for chunk_id, chunk_entities in entities_by_chunk.items():
        for i in range(len(chunk_entities) - 1):
            source = chunk_entities[i]
            target = chunk_entities[i + 1]
            pair = (source["id"], target["id"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            relationships.append({
                "id": f"rel-{uuid.uuid4().hex[:12]}",
                "source_entity_id": source["id"],
                "target_entity_id": target["id"],
                "relationship_type": "CONTAINS",
                "description": f"Co-located entities in document {document_id}",
                "properties": {"document_id": document_id},
            })

    # Detect REFERENCES between entities across chunks using keyword overlap
    all_entities = list(entities)
    for i in range(len(all_entities)):
        for j in range(i + 1, min(i + 5, len(all_entities))):
            source = all_entities[i]
            target = all_entities[j]
            # Skip same-chunk pairs (already handled above)
            if source["source_chunk_id"] == target["source_chunk_id"]:
                continue
            pair = (source["id"], target["id"])
            if pair in seen_pairs:
                continue
            # Check for keyword overlap in names
            source_words = set(source["name"].lower().split())
            target_words = set(target["name"].lower().split())
            if source_words & target_words:
                seen_pairs.add(pair)
                relationships.append({
                    "id": f"rel-{uuid.uuid4().hex[:12]}",
                    "source_entity_id": source["id"],
                    "target_entity_id": target["id"],
                    "relationship_type": "REFERENCES",
                    "description": f"Cross-reference between entities in document {document_id}",
                    "properties": {"document_id": document_id},
                })

    return relationships

"""Ingestion Agent — orchestrates the document processing pipeline.

This agent handles the full ingestion flow: validate → normalize → chunk →
extract entities → deduplicate → index → emit event.

It uses the domain processing components (normalizers, chunkers) and port
interfaces to coordinate the multi-step ingestion pipeline with intelligent
error handling and strategy selection.
"""

from __future__ import annotations

from typing import Any

import structlog
from strands import Agent, tool

from src.agents.base import AgentConfig, create_agent
from src.domain.events.bus import EventBus
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.normalizer import DocumentNormalizer
from src.ports.document_store import DocumentStorePort
from src.ports.embedding import EmbeddingPort
from src.ports.graph_store import GraphStorePort
from src.ports.sparse_index import SparseIndexPort
from src.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)

# Deduplication threshold (cosine similarity)
DEDUP_THRESHOLD = 0.95


def _build_ingestion_tools(
    document_store: DocumentStorePort,
    normalizer: DocumentNormalizer,
    chunker_factory: ChunkerFactory,
    embedding_port: EmbeddingPort,
    vector_store: VectorStorePort,
    sparse_index: SparseIndexPort,
    graph_store: GraphStorePort,
    event_bus: EventBus,
) -> list[Any]:
    """Build Strands tool functions for the ingestion pipeline."""

    @tool
    def validate_document(document_id: str) -> str:
        """Validate a document exists and is ready for processing.

        Retrieves the document from the store and validates its format,
        size, and content are acceptable for ingestion.

        Args:
            document_id: The UUID of the document to validate.
        """
        import asyncio

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            # Basic validation
            issues = []
            if doc.size_bytes == 0:
                issues.append("Document is empty (0 bytes)")
            if doc.size_bytes > 50 * 1024 * 1024:  # 50MB limit
                issues.append(f"Document exceeds 50MB limit ({doc.size_bytes} bytes)")
            if not doc.content:
                issues.append("Document content is null/empty")

            return {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "format": doc.format.value,
                "size_bytes": doc.size_bytes,
                "valid": len(issues) == 0,
                "issues": issues,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def normalize_document(document_id: str) -> str:
        """Normalize a document to plaintext with section metadata.

        Dispatches to the appropriate format-specific normalizer (Markdown,
        HTML, PDF, or plaintext) and produces clean text with section boundaries.

        Args:
            document_id: The UUID of the document to normalize.
        """
        import asyncio

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            normalized = normalizer.normalize(doc)
            return {
                "document_id": str(doc.id),
                "normalized_id": str(normalized.id),
                "plaintext_length": len(normalized.plaintext),
                "section_count": len(normalized.sections),
                "sections": [
                    {"heading": s.heading, "level": s.level}
                    for s in normalized.sections[:10]
                ],
                "format": doc.format.value,
                "success": True,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def chunk_document(
        document_id: str,
        strategy: str = "recursive",
    ) -> str:
        """Split a normalized document into chunks using the specified strategy.

        Available strategies:
        - "fixed_size": Fixed character size with overlap (good baseline)
        - "recursive": Splits by section headers (structure-aware, recommended)
        - "semantic": Splits at embedding similarity boundaries (most accurate, slower)

        Args:
            document_id: The UUID of the document to chunk.
            strategy: Chunking strategy to use (default: recursive).
        """
        import asyncio

        from src.domain.models.enums import ChunkingStrategy

        strategy_map = {
            "fixed_size": ChunkingStrategy.FIXED_SIZE,
            "recursive": ChunkingStrategy.RECURSIVE,
            "semantic": ChunkingStrategy.SEMANTIC,
        }

        if strategy not in strategy_map:
            return str({
                "error": f"Unknown strategy: {strategy}. Use: {list(strategy_map.keys())}",
                "success": False,
            })

        chunking_strategy = strategy_map[strategy]

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            normalized = normalizer.normalize(doc)
            chunker = chunker_factory.get_chunker(chunking_strategy)
            chunks = chunker.chunk(normalized)

            return {
                "document_id": document_id,
                "strategy": strategy,
                "chunk_count": len(chunks),
                "chunks_preview": [
                    {
                        "id": str(c.id),
                        "index": c.index,
                        "char_count": c.char_count,
                        "section": c.section_heading,
                        "text_preview": c.text[:100],
                    }
                    for c in chunks[:5]
                ],
                "total_chars": sum(c.char_count for c in chunks),
                "avg_chunk_size": (
                    sum(c.char_count for c in chunks) // len(chunks) if chunks else 0
                ),
                "success": True,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def deduplicate_chunks(document_id: str, strategy: str = "recursive") -> str:
        """Check chunks for near-duplicates against existing indexed content.

        Computes embeddings for new chunks and compares against the vector
        store. Flags chunks with cosine similarity > 0.95 as duplicates.

        Args:
            document_id: The UUID of the document whose chunks to check.
            strategy: The chunking strategy used (to reproduce chunks).
        """
        import asyncio

        from src.domain.models.enums import ChunkingStrategy

        strategy_map = {
            "fixed_size": ChunkingStrategy.FIXED_SIZE,
            "recursive": ChunkingStrategy.RECURSIVE,
            "semantic": ChunkingStrategy.SEMANTIC,
        }

        chunking_strategy = strategy_map.get(strategy, ChunkingStrategy.RECURSIVE)

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            normalized = normalizer.normalize(doc)
            chunker = chunker_factory.get_chunker(chunking_strategy)
            chunks = chunker.chunk(normalized)

            if not chunks:
                return {"duplicates": [], "unique_count": 0, "total_count": 0}

            # Embed all chunks
            texts = [c.text for c in chunks]
            embeddings = await embedding_port.embed(texts)

            # Check each against existing store
            duplicates = []
            unique_chunks = []

            for chunk, embedding in zip(chunks, embeddings, strict=True):
                similar = await vector_store.search(embedding, top_k=1)
                if similar and similar[0].score > DEDUP_THRESHOLD:
                    duplicates.append({
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.index,
                        "similar_to": str(similar[0].chunk.id),
                        "similarity": similar[0].score,
                    })
                else:
                    unique_chunks.append(str(chunk.id))

            return {
                "document_id": document_id,
                "total_chunks": len(chunks),
                "unique_count": len(unique_chunks),
                "duplicate_count": len(duplicates),
                "duplicates": duplicates[:10],
                "dedup_threshold": DEDUP_THRESHOLD,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def index_chunks(document_id: str, strategy: str = "recursive") -> str:
        """Index document chunks into vector store and sparse index.

        Embeds chunks and stores them in both the dense vector store
        and the BM25 sparse index for hybrid search.

        Args:
            document_id: The UUID of the document to index.
            strategy: The chunking strategy to use.
        """
        import asyncio

        from src.domain.models.entities import EmbeddingRecord
        from src.domain.models.enums import ChunkingStrategy

        strategy_map = {
            "fixed_size": ChunkingStrategy.FIXED_SIZE,
            "recursive": ChunkingStrategy.RECURSIVE,
            "semantic": ChunkingStrategy.SEMANTIC,
        }

        chunking_strategy = strategy_map.get(strategy, ChunkingStrategy.RECURSIVE)

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            normalized = normalizer.normalize(doc)
            chunker = chunker_factory.get_chunker(chunking_strategy)
            chunks = chunker.chunk(normalized)

            if not chunks:
                return {
                    "document_id": document_id,
                    "indexed": False,
                    "reason": "No chunks produced",
                }

            # Generate embeddings
            texts = [c.text for c in chunks]
            embeddings = await embedding_port.embed(texts)

            # Store in vector store
            embedding_records = [
                EmbeddingRecord(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    vector=emb,
                    metadata={
                        "section": chunk.section_heading,
                        "strategy": chunk.strategy.value,
                        "char_count": chunk.char_count,
                        "index": chunk.index,
                    },
                )
                for chunk, emb in zip(chunks, embeddings, strict=True)
            ]

            await vector_store.store(embedding_records)

            # Store in sparse index
            await sparse_index.index(chunks)

            return {
                "document_id": document_id,
                "indexed": True,
                "chunks_indexed": len(chunks),
                "vector_store": "stored",
                "sparse_index": "stored",
                "strategy": strategy,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def extract_entities(document_id: str, strategy: str = "recursive") -> str:
        """Extract entities and relationships from document chunks for the knowledge graph.

        Uses LLM-based extraction to identify entities (people, concepts,
        technologies) and their relationships from the document content.

        Args:
            document_id: The UUID of the document to extract from.
            strategy: The chunking strategy used.
        """
        import asyncio
        import uuid as uuid_mod

        from src.domain.models.entities import ExtractedEntity, ExtractedRelationship
        from src.domain.models.enums import ChunkingStrategy

        strategy_map = {
            "fixed_size": ChunkingStrategy.FIXED_SIZE,
            "recursive": ChunkingStrategy.RECURSIVE,
            "semantic": ChunkingStrategy.SEMANTIC,
        }

        chunking_strategy = strategy_map.get(strategy, ChunkingStrategy.RECURSIVE)

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)
            normalized = normalizer.normalize(doc)
            chunker = chunker_factory.get_chunker(chunking_strategy)
            chunks = chunker.chunk(normalized)

            # Extract entities from chunk text (simplified extraction)
            # In production, this would use Instructor + Pydantic for structured extraction
            all_entities: list[ExtractedEntity] = []
            all_relationships: list[ExtractedRelationship] = []

            for chunk in chunks[:20]:  # Limit to first 20 chunks for efficiency
                # Basic entity extraction via keyword analysis
                # Capitalized multi-word phrases as candidate entities
                import re

                entity_candidates = re.findall(
                    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", chunk.text
                )

                for entity_name in set(entity_candidates[:5]):
                    entity = ExtractedEntity(
                        id=uuid_mod.uuid4(),
                        name=entity_name,
                        entity_type="Concept",
                        description=f"Entity extracted from: {chunk.section_heading}",
                        source_chunk_id=chunk.id,
                    )
                    all_entities.append(entity)

            # Store in graph
            if all_entities:
                await graph_store.store_entities(all_entities)

            if all_relationships:
                await graph_store.store_relationships(all_relationships)

            return {
                "document_id": document_id,
                "entities_extracted": len(all_entities),
                "relationships_extracted": len(all_relationships),
                "entity_preview": [
                    {"name": e.name, "type": e.entity_type}
                    for e in all_entities[:10]
                ],
                "success": True,
            }

        result = asyncio.run(_run())
        return str(result)

    @tool
    def emit_ingestion_event(
        document_id: str,
        chunk_count: int,
        entity_count: int,
    ) -> str:
        """Emit a DocumentIngestedEvent after successful processing.

        Publishes a domain event signaling that document ingestion is complete,
        allowing other system components to react (e.g., update indexes, notify users).

        Args:
            document_id: The UUID of the ingested document.
            chunk_count: Number of chunks produced.
            entity_count: Number of entities extracted.
        """
        import asyncio
        from datetime import datetime

        from src.domain.events.events import DocumentIngestedEvent

        async def _run() -> dict[str, Any]:
            doc = await document_store.retrieve(document_id)

            event = DocumentIngestedEvent(
                document_id=doc.id,
                format=doc.format,
                size_bytes=doc.size_bytes,
                timestamp=datetime.utcnow(),
                chunk_count=chunk_count,
                entity_count=entity_count,
            )

            await event_bus.publish(event)

            return {
                "event_published": True,
                "document_id": document_id,
                "event_type": "DocumentIngestedEvent",
                "chunk_count": chunk_count,
                "entity_count": entity_count,
            }

        result = asyncio.run(_run())
        return str(result)

    return [
        validate_document,
        normalize_document,
        chunk_document,
        deduplicate_chunks,
        index_chunks,
        extract_entities,
        emit_ingestion_event,
    ]


INGESTION_SYSTEM_PROMPT = """You are an Ingestion Agent for a RAG (Retrieval-Augmented Generation) pipeline.

Your job is to process uploaded documents through the complete ingestion pipeline.

## Ingestion Pipeline (execute in this exact order)

1. **Validate** — Use validate_document to check the document is ready.
   - If validation fails, report the issues and STOP.

2. **Normalize** — Use normalize_document to convert to clean plaintext with sections.
   - If normalization fails, report the error and STOP.

3. **Chunk** — Use chunk_document to split into indexable segments.
   - Choose strategy based on document characteristics:
     - "recursive" (default): Best for structured documents with clear headings
     - "fixed_size": Fallback for unstructured text
     - "semantic": Best for long documents where topic boundaries matter (slower)

4. **Deduplicate** — Use deduplicate_chunks to check for near-duplicate content.
   - Report duplicate count but continue with unique chunks.

5. **Index** — Use index_chunks to store in vector and sparse indexes.
   - This makes the content searchable.

6. **Extract entities** — Use extract_entities to populate the knowledge graph.
   - This enables graph-based retrieval.

7. **Emit event** — Use emit_ingestion_event to signal completion.
   - Include final chunk_count and entity_count.

## Strategy Selection Guidelines

- **Markdown/HTML** with clear headings → "recursive"
- **PDF** documents → "recursive" (preserves page/section structure)
- **Plain text** without structure → "fixed_size"
- **Long technical documents** → "semantic" (identifies topic boundaries)

## Error Handling

- If any step fails, log the error and report which step failed
- For non-critical failures (deduplication, entity extraction), continue the pipeline
- For critical failures (validation, normalization), stop immediately
- Always provide a final summary of what was accomplished

## Output Format

Provide a structured summary at the end:
- Document ID, filename, format
- Chunks produced (count + strategy used)
- Duplicates found
- Entities extracted
- Overall status (success/partial/failed)
"""


def create_ingestion_agent(
    document_store: DocumentStorePort,
    normalizer: DocumentNormalizer,
    chunker_factory: ChunkerFactory,
    embedding_port: EmbeddingPort,
    vector_store: VectorStorePort,
    sparse_index: SparseIndexPort,
    graph_store: GraphStorePort,
    event_bus: EventBus,
    config: AgentConfig | None = None,
) -> Agent:
    """Create an Ingestion Agent for document processing pipeline.

    Args:
        document_store: Port for document storage/retrieval.
        normalizer: Document normalizer orchestrator.
        chunker_factory: Factory for chunking strategy selection.
        embedding_port: Port for generating embeddings.
        vector_store: Port for dense vector storage.
        sparse_index: Port for BM25 sparse indexing.
        graph_store: Port for knowledge graph storage.
        event_bus: Event bus for publishing domain events.
        config: Optional agent configuration.

    Returns:
        A Strands Agent configured for document ingestion.
    """
    tools = _build_ingestion_tools(
        document_store,
        normalizer,
        chunker_factory,
        embedding_port,
        vector_store,
        sparse_index,
        graph_store,
        event_bus,
    )

    agent = create_agent(
        tools=tools,
        system_prompt=INGESTION_SYSTEM_PROMPT,
        config=config,
    )

    logger.info("ingestion_agent.created", tool_count=len(tools))
    return agent

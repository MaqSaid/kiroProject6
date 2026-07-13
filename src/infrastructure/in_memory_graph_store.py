"""In-memory Graph Store stub for GraphStorePort.

Lightweight stub that stores entities and relationships in memory.
Returns empty results for traversal queries. Satisfies the port
interface so the pipeline works without Neo4j/Neptune running.

Replace with Neo4jGraphStore or NeptuneGraphStore for production.
"""

from __future__ import annotations

import structlog

from src.domain.models.entities import ExtractedEntity, ExtractedRelationship, ScoredChunk
from src.ports.graph_store import GraphStorePort  # noqa: F401

logger = structlog.get_logger(__name__)


class InMemoryGraphStore:
    """In-memory stub implementing GraphStorePort.

    Stores entities and relationships in dicts. Traversal returns
    empty results (graph search is optional — pipeline degrades gracefully).
    """

    def __init__(self) -> None:
        self._entities: list[ExtractedEntity] = []
        self._relationships: list[ExtractedRelationship] = []
        logger.info("in_memory_graph_store.initialized")

    async def store_entities(self, entities: list[ExtractedEntity]) -> None:
        """Store entities in memory."""
        self._entities.extend(entities)
        logger.info("in_memory_graph_store.store_entities", count=len(entities))

    async def store_relationships(self, relationships: list[ExtractedRelationship]) -> None:
        """Store relationships in memory."""
        self._relationships.extend(relationships)
        logger.info("in_memory_graph_store.store_relationships", count=len(relationships))

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        """Stub: returns empty results. Replace with Neo4j Cypher for real traversal."""
        logger.debug("in_memory_graph_store.traverse.stub", query=query[:50], max_hops=max_hops)
        return []

    async def delete_by_document(self, document_id: str) -> None:
        """Remove all entities/relationships for a document."""
        before = len(self._entities)
        self._entities = [
            e for e in self._entities
            if str(e.source_chunk_id) != document_id
        ]
        self._relationships = [
            r for r in self._relationships
            if str(r.source_chunk_id) != document_id
        ]
        logger.info(
            "in_memory_graph_store.delete_by_document",
            document_id=document_id,
            removed=before - len(self._entities),
        )

    @property
    def entity_count(self) -> int:
        """Return number of stored entities."""
        return len(self._entities)

    @property
    def relationship_count(self) -> int:
        """Return number of stored relationships."""
        return len(self._relationships)

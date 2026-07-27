"""In-memory Graph Store stub for GraphStorePort.

Lightweight stub that stores entities and relationships in memory.
Returns empty results for traversal queries. Satisfies the port
interface so the pipeline works without Neo4j/Neptune running.

Replace with Neo4jGraphStore or NeptuneGraphStore for production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.ports.graph_store import GraphStorePort  # noqa: F401

if TYPE_CHECKING:
    from src.domain.models.entities import ExtractedEntity, ExtractedRelationship, ScoredChunk

logger = structlog.get_logger(__name__)


class GraphStoreError(Exception):
    """Raised when graph store operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


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
        """Store entities in memory.

        Args:
            entities: List of extracted entities to store.

        Raises:
            GraphStoreError: If storage fails.
        """
        try:
            self._entities.extend(entities)
            logger.info(
                "in_memory_graph_store.store_entities.success",
                count=len(entities),
                total=len(self._entities),
            )
        except Exception as e:
            logger.error(
                "in_memory_graph_store.store_entities.failed",
                error=str(e),
                count=len(entities),
            )
            raise GraphStoreError(
                f"Failed to store entities: {e}",
                operation="store_entities",
            ) from e

    async def store_relationships(self, relationships: list[ExtractedRelationship]) -> None:
        """Store relationships in memory.

        Args:
            relationships: List of extracted relationships to store.

        Raises:
            GraphStoreError: If storage fails.
        """
        try:
            self._relationships.extend(relationships)
            logger.info(
                "in_memory_graph_store.store_relationships.success",
                count=len(relationships),
                total=len(self._relationships),
            )
        except Exception as e:
            logger.error(
                "in_memory_graph_store.store_relationships.failed",
                error=str(e),
                count=len(relationships),
            )
            raise GraphStoreError(
                f"Failed to store relationships: {e}",
                operation="store_relationships",
            ) from e

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        """Stub: returns empty results. Replace with Neo4j Cypher for real traversal.

        Args:
            query: The traversal query text.
            max_hops: Maximum graph hops (unused in stub).

        Returns:
            Empty list (stub implementation).
        """
        try:
            logger.debug(
                "in_memory_graph_store.traverse.stub",
                query=query[:50],
                max_hops=max_hops,
            )
            return []
        except Exception as e:
            logger.error(
                "in_memory_graph_store.traverse.failed",
                error=str(e),
                query=query[:50],
            )
            raise GraphStoreError(
                f"Failed to traverse graph: {e}",
                operation="traverse",
            ) from e

    async def delete_by_document(self, document_id: str) -> None:
        """Remove all entities/relationships for a document.

        Args:
            document_id: The document UUID string whose data to remove.

        Raises:
            GraphStoreError: If deletion fails.
        """
        try:
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
                "in_memory_graph_store.delete_by_document.success",
                document_id=document_id,
                removed=before - len(self._entities),
            )
        except Exception as e:
            logger.error(
                "in_memory_graph_store.delete_by_document.failed",
                error=str(e),
                document_id=document_id,
            )
            raise GraphStoreError(
                f"Failed to delete document from graph: {e}",
                operation="delete_by_document",
            ) from e

    @property
    def entity_count(self) -> int:
        """Return number of stored entities."""
        return len(self._entities)

    @property
    def relationship_count(self) -> int:
        """Return number of stored relationships."""
        return len(self._relationships)

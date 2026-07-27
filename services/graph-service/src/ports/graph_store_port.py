"""GraphStorePort protocol interface for graph storage operations."""

from typing import Protocol

from domain_models import ExtractedEntity, ExtractedRelationship, ScoredChunk


class GraphStorePort(Protocol):
    """Protocol defining the interface for graph storage implementations."""

    async def initialize(self) -> None:
        """Initialize the graph store (create indexes, verify connectivity)."""
        ...

    async def store_entities(self, entities: list[ExtractedEntity]) -> int:
        """Store entities in the graph using MERGE by entity id.

        Args:
            entities: List of entities to store.

        Returns:
            Number of entities stored.
        """
        ...

    async def store_relationships(
        self, relationships: list[ExtractedRelationship]
    ) -> tuple[int, int]:
        """Store relationships in the graph using MERGE by relationship id.

        Skips relationships where source or target entity does not exist.

        Args:
            relationships: List of relationships to store.

        Returns:
            Tuple of (stored_count, skipped_count).
        """
        ...

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        """Execute a graph traversal query with variable-length paths.

        Args:
            query: Query text for traversal matching.
            max_hops: Maximum traversal depth (capped at 5).

        Returns:
            List of scored chunks from graph traversal.
        """
        ...

    async def delete_by_document(self, document_id: str) -> tuple[int, int]:
        """Delete all nodes for a document_id and connected relationships.

        Args:
            document_id: The document ID whose entities should be deleted.

        Returns:
            Tuple of (deleted_nodes, deleted_relationships).
        """
        ...

    async def close(self) -> None:
        """Close the graph store connection."""
        ...

    async def verify_connectivity(self) -> bool:
        """Verify the graph store is reachable.

        Returns:
            True if connectivity check passes, False otherwise.
        """
        ...

    async def verify_indexes(self) -> bool:
        """Verify that required indexes exist.

        Returns:
            True if all required indexes are present, False otherwise.
        """
        ...

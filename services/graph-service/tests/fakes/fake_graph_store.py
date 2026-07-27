"""In-memory fake of the GraphStorePort for fast property testing without Neo4j.

Implements the same interface as Neo4jGraphStore but stores data in Python dicts.
Supports entity MERGE, relationship deduplication, BFS traversal with scoring,
and document deletion.
"""

from collections import deque
from typing import Any

from domain_models import ExtractedEntity, ExtractedRelationship, ScoredChunk


class FakeGraphStore:
    """In-memory graph store implementing GraphStorePort protocol.

    Stores entities in a dict keyed by id. Stores relationships in a dict keyed
    by id, checking that both endpoints exist. Implements BFS traversal scoring
    by hop distance. Implements delete_by_document by filtering source_chunk_id prefix.
    """

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}
        self._relationships: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """No-op for in-memory store."""
        pass

    async def store_entities(self, entities: list[ExtractedEntity]) -> int:
        """Store entities using MERGE semantics (overwrite on existing id)."""
        count = 0
        for entity in entities:
            self._entities[entity.id] = {
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.entity_type.value,
                "description": entity.description,
                "source_chunk_id": entity.source_chunk_id,
                "properties": dict(entity.properties),
            }
            count += 1
        return count

    async def store_relationships(
        self, relationships: list[ExtractedRelationship]
    ) -> tuple[int, int]:
        """Store relationships with MERGE by id. Skip if endpoints don't exist."""
        stored = 0
        skipped = 0
        for rel in relationships:
            if rel.source_entity_id not in self._entities:
                skipped += 1
                continue
            if rel.target_entity_id not in self._entities:
                skipped += 1
                continue
            self._relationships[rel.id] = {
                "id": rel.id,
                "source_entity_id": rel.source_entity_id,
                "target_entity_id": rel.target_entity_id,
                "relationship_type": rel.relationship_type.value,
                "description": rel.description,
                "properties": dict(rel.properties),
            }
            stored += 1
        return stored, skipped

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        """BFS traversal from matching start nodes, scoring by 1/(1+hop_distance).

        max_hops is capped at 5.
        """
        effective_max_hops = min(max_hops, 5)

        start_nodes: set[str] = set()
        for eid, entity in self._entities.items():
            if query in entity["name"] or query == entity["entity_type"]:
                start_nodes.add(eid)

        if not start_nodes:
            return []

        adjacency: dict[str, set[str]] = {}
        for rel in self._relationships.values():
            src = rel["source_entity_id"]
            tgt = rel["target_entity_id"]
            if src in self._entities and tgt in self._entities:
                adjacency.setdefault(src, set()).add(tgt)
                adjacency.setdefault(tgt, set()).add(src)

        distances: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque()

        for start_id in start_nodes:
            if start_id not in distances:
                distances[start_id] = 0
            queue.append((start_id, 0))

        visited: set[str] = set(start_nodes)

        while queue:
            current_id, current_dist = queue.popleft()
            if current_dist >= effective_max_hops:
                continue
            for neighbor_id in adjacency.get(current_id, set()):
                new_dist = current_dist + 1
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    distances[neighbor_id] = new_dist
                    queue.append((neighbor_id, new_dist))
                elif new_dist < distances.get(neighbor_id, float("inf")):
                    distances[neighbor_id] = new_dist
                    queue.append((neighbor_id, new_dist))

        results: list[ScoredChunk] = []
        for eid, hop_distance in distances.items():
            if hop_distance == 0:
                continue
            entity = self._entities[eid]
            score = 1.0 / (1 + hop_distance)
            results.append(
                ScoredChunk(
                    chunk_id=entity["id"],
                    document_id=entity["source_chunk_id"],
                    text=entity["description"],
                    section_heading=entity["name"],
                    score=score,
                    retrieval_method="graph",
                )
            )

        results.sort(key=lambda c: c.score, reverse=True)
        return results[:20]

    async def delete_by_document(self, document_id: str) -> tuple[int, int]:
        """Delete all entities whose source_chunk_id starts with document_id,
        and all relationships connected to those entities."""
        entities_to_delete: set[str] = set()
        for eid, entity in self._entities.items():
            if entity["source_chunk_id"].startswith(document_id):
                entities_to_delete.add(eid)

        rels_to_delete: set[str] = set()
        for rid, rel in self._relationships.items():
            if (
                rel["source_entity_id"] in entities_to_delete
                or rel["target_entity_id"] in entities_to_delete
            ):
                rels_to_delete.add(rid)

        for eid in entities_to_delete:
            del self._entities[eid]
        for rid in rels_to_delete:
            del self._relationships[rid]

        return len(entities_to_delete), len(rels_to_delete)

    async def close(self) -> None:
        """No-op for in-memory store."""
        pass

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get a stored entity by id."""
        return self._entities.get(entity_id)

    def get_relationship(self, rel_id: str) -> dict[str, Any] | None:
        """Get a stored relationship by id."""
        return self._relationships.get(rel_id)

    @property
    def entity_count(self) -> int:
        """Number of stored entities."""
        return len(self._entities)

    @property
    def relationship_count(self) -> int:
        """Number of stored relationships."""
        return len(self._relationships)

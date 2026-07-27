"""Neo4jGraphStore adapter implementing GraphStorePort with async driver."""

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ClientError, ServiceUnavailable, SessionExpired

from domain_models import ExtractedEntity, ExtractedRelationship, ScoredChunk
from src.config import Settings

logger = structlog.get_logger(__name__)


class GraphStoreUnavailableError(Exception):
    """Raised when Neo4j is unavailable or a query times out."""

    pass


class Neo4jGraphStore:
    """Neo4j adapter implementing the GraphStorePort protocol.

    Uses async driver with connection pool (10-50), per-query timeout (5s),
    and parameterized Cypher queries exclusively.
    """

    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    @classmethod
    async def create(cls, settings: Settings) -> "Neo4jGraphStore":
        """Factory method to create a Neo4jGraphStore with configured driver."""
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_pool_size,
            connection_acquisition_timeout=settings.neo4j_connection_timeout,
        )
        return cls(driver=driver, database=settings.neo4j_database)

    async def initialize(self) -> None:
        """Create indexes on entity_type and source_chunk_id during startup."""
        logger.info("neo4j.initializing", database=self._database)
        await self._execute_write(
            "CREATE INDEX IF NOT EXISTS FOR (e:LegalEntity) ON (e.entity_type)",
            {},
            operation="create_index_entity_type",
        )
        await self._execute_write(
            "CREATE INDEX IF NOT EXISTS FOR (e:LegalEntity) ON (e.source_chunk_id)",
            {},
            operation="create_index_source_chunk_id",
        )
        logger.info("neo4j.initialized", database=self._database)

    async def store_entities(self, entities: list[ExtractedEntity]) -> int:
        """Store entities using MERGE by entity id with all properties.

        Uses UNWIND for batch processing with parameterized queries.
        """
        if not entities:
            return 0

        query = """
        UNWIND $entities AS entity
        MERGE (e:LegalEntity {id: entity.id})
        SET e.name = entity.name,
            e.entity_type = entity.entity_type,
            e.description = entity.description,
            e.source_chunk_id = entity.source_chunk_id
        SET e += entity.properties
        RETURN count(e) AS stored_count
        """
        params = {
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type.value,
                    "description": e.description,
                    "source_chunk_id": e.source_chunk_id,
                    "properties": e.properties,
                }
                for e in entities
            ]
        }
        records = await self._execute_write(
            query, params, operation="store_entities"
        )
        stored_count = records[0]["stored_count"] if records else 0
        logger.info("entities.stored", count=stored_count)
        return stored_count

    async def store_relationships(
        self, relationships: list[ExtractedRelationship]
    ) -> tuple[int, int]:
        """Store relationships with MERGE by relationship id.

        Skips relationships with missing endpoints and logs warning.
        Uses OPTIONAL MATCH for source/target to detect missing endpoints.
        """
        if not relationships:
            return 0, 0

        stored_count = 0
        skipped_count = 0

        query = """
        UNWIND $relationships AS rel
        OPTIONAL MATCH (source:LegalEntity {id: rel.source_entity_id})
        OPTIONAL MATCH (target:LegalEntity {id: rel.target_entity_id})
        WITH rel, source, target
        WHERE source IS NOT NULL AND target IS NOT NULL
        MERGE (source)-[r:RELATES_TO {id: rel.id}]->(target)
        SET r.relationship_type = rel.relationship_type,
            r.description = rel.description
        SET r += rel.properties
        RETURN count(r) AS stored_count
        """
        params = {
            "relationships": [
                {
                    "id": r.id,
                    "source_entity_id": r.source_entity_id,
                    "target_entity_id": r.target_entity_id,
                    "relationship_type": r.relationship_type.value,
                    "description": r.description,
                    "properties": r.properties,
                }
                for r in relationships
            ]
        }
        records = await self._execute_write(
            query, params, operation="store_relationships"
        )
        stored_count = records[0]["stored_count"] if records else 0
        skipped_count = len(relationships) - stored_count

        if skipped_count > 0:
            logger.warning(
                "relationships.skipped_missing_endpoints",
                skipped_count=skipped_count,
                total=len(relationships),
            )

        logger.info(
            "relationships.stored",
            stored_count=stored_count,
            skipped_count=skipped_count,
        )
        return stored_count, skipped_count

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        """Execute variable-length Cypher path query.

        max_hops is capped at 5. Scoring by 1.0/(1+hop_distance).
        """
        # Cap max_hops at 5
        effective_max_hops = min(max_hops, 5)

        cypher = """
        MATCH (start:LegalEntity)
        WHERE start.name CONTAINS $query OR start.entity_type = $query
        MATCH path = (start)-[*1..""" + str(effective_max_hops) + """]-(related:LegalEntity)
        WHERE related <> start
        WITH related, min(length(path)) AS hop_distance
        RETURN related.id AS chunk_id,
               related.source_chunk_id AS document_id,
               related.description AS text,
               related.name AS section_heading,
               1.0 / (1 + hop_distance) AS score,
               'graph' AS retrieval_method
        ORDER BY score DESC
        LIMIT 20
        """
        params = {"query": query}
        records = await self._execute_read(
            cypher, params, operation="traverse"
        )

        results = []
        for record in records:
            results.append(
                ScoredChunk(
                    chunk_id=record["chunk_id"],
                    document_id=record["document_id"] or "",
                    text=record["text"] or "",
                    section_heading=record["section_heading"] or "",
                    score=record["score"],
                    retrieval_method=record["retrieval_method"],
                )
            )

        logger.info(
            "traverse.completed",
            query=query[:100],
            max_hops=effective_max_hops,
            results_count=len(results),
        )
        return results

    async def delete_by_document(self, document_id: str) -> tuple[int, int]:
        """Remove all nodes for a document_id and connected relationships.

        Uses DETACH DELETE in a single transaction for atomicity.
        Uses STARTS WITH to match all chunk IDs belonging to the document.
        """
        # Count relationships before deletion for reporting
        count_query = """
        MATCH (e:LegalEntity)
        WHERE e.source_chunk_id STARTS WITH $document_id_prefix
        OPTIONAL MATCH (e)-[r]-()
        RETURN count(DISTINCT e) AS node_count, count(DISTINCT r) AS rel_count
        """
        count_records = await self._execute_read(
            count_query,
            {"document_id_prefix": document_id},
            operation="delete_by_document_count",
        )

        node_count = count_records[0]["node_count"] if count_records else 0
        rel_count = count_records[0]["rel_count"] if count_records else 0

        # Perform the deletion
        delete_query = """
        MATCH (e:LegalEntity)
        WHERE e.source_chunk_id STARTS WITH $document_id_prefix
        DETACH DELETE e
        """
        await self._execute_write(
            delete_query,
            {"document_id_prefix": document_id},
            operation="delete_by_document",
        )

        logger.info(
            "document.deleted",
            document_id=document_id,
            deleted_nodes=node_count,
            deleted_relationships=rel_count,
        )
        return node_count, rel_count

    async def verify_connectivity(self) -> bool:
        """Verify Neo4j connectivity for health checks."""
        try:
            await self._driver.verify_connectivity()
            return True
        except (ServiceUnavailable, SessionExpired) as e:
            logger.error("neo4j.connectivity_failed", error=str(e))
            return False

    async def verify_indexes(self) -> bool:
        """Verify that required indexes exist on entity_type and source_chunk_id."""
        try:
            query = "SHOW INDEXES YIELD labelsOrTypes, properties RETURN labelsOrTypes, properties"
            records = await self._execute_read(query, {}, operation="verify_indexes")
            # Check for both required indexes
            has_entity_type_index = False
            has_source_chunk_id_index = False
            for record in records:
                labels = record.get("labelsOrTypes", [])
                properties = record.get("properties", [])
                if "LegalEntity" in labels:
                    if "entity_type" in properties:
                        has_entity_type_index = True
                    if "source_chunk_id" in properties:
                        has_source_chunk_id_index = True
            return has_entity_type_index and has_source_chunk_id_index
        except Exception as e:
            logger.error("neo4j.verify_indexes_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close the Neo4j driver."""
        await self._driver.close()
        logger.info("neo4j.driver_closed")

    async def _execute_read(
        self, query: str, params: dict, operation: str
    ) -> list[dict]:
        """Execute a read query with timeout and error handling."""
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(query, params, timeout=5.0)
                return [record.data() async for record in result]
        except (ServiceUnavailable, SessionExpired) as e:
            logger.error("neo4j_unavailable", operation=operation, error=str(e))
            raise GraphStoreUnavailableError(f"Neo4j unavailable: {e}") from e
        except ClientError as e:
            if "transaction has been terminated" in str(e):
                logger.error(
                    "neo4j_timeout", operation=operation, query=query[:100]
                )
                raise GraphStoreUnavailableError(f"Query timeout: {e}") from e
            raise

    async def _execute_write(
        self, query: str, params: dict, operation: str
    ) -> list[dict]:
        """Execute a write query with timeout and error handling."""
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(query, params, timeout=5.0)
                return [record.data() async for record in result]
        except (ServiceUnavailable, SessionExpired) as e:
            logger.error("neo4j_unavailable", operation=operation, error=str(e))
            raise GraphStoreUnavailableError(f"Neo4j unavailable: {e}") from e
        except ClientError as e:
            if "transaction has been terminated" in str(e):
                logger.error(
                    "neo4j_timeout", operation=operation, query=query[:100]
                )
                raise GraphStoreUnavailableError(f"Query timeout: {e}") from e
            raise

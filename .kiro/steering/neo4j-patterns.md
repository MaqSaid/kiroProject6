---
inclusion: fileMatch
fileMatchPattern: services/graph-service/**
---

# Neo4j Patterns Guide

## MERGE Pattern for Idempotent Entity Upserts

Always use MERGE with the entity `id` as the merge key to ensure idempotent operations:

```cypher
UNWIND $entities AS entity
MERGE (e:LegalEntity {id: entity.id})
SET e.name = entity.name,
    e.entity_type = entity.entity_type,
    e.description = entity.description,
    e.source_chunk_id = entity.source_chunk_id
SET e += entity.properties
```

For relationships, MERGE by relationship `id`:

```cypher
UNWIND $relationships AS rel
MATCH (source:LegalEntity {id: rel.source_entity_id})
MATCH (target:LegalEntity {id: rel.target_entity_id})
CALL apoc.merge.relationship(source, rel.relationship_type, {id: rel.id}, rel.properties, target) YIELD rel AS r
RETURN r
```

If APOC is unavailable, use dynamic relationship creation:

```cypher
UNWIND $relationships AS rel
MATCH (source:LegalEntity {id: rel.source_entity_id})
MATCH (target:LegalEntity {id: rel.target_entity_id})
MERGE (source)-[r:RELATES_TO {id: rel.id}]->(target)
SET r.relationship_type = rel.relationship_type,
    r.description = rel.description
SET r += rel.properties
```

## Variable-Length Traversal Queries

Graph traversal for scoring by hop distance:

```cypher
MATCH (start:LegalEntity)
WHERE start.name CONTAINS $query OR start.entity_type = $entity_type
MATCH path = (start)-[*1..$max_hops]-(related:LegalEntity)
WITH related, min(length(path)) AS hop_distance
RETURN related.id AS chunk_id,
       related.source_chunk_id AS document_id,
       related.description AS text,
       related.name AS section_heading,
       1.0 / (1 + hop_distance) AS score,
       'graph' AS retrieval_method
ORDER BY score DESC
LIMIT 20
```

Key rules:
- Cap `max_hops` at 5 regardless of input
- Score formula: `1.0 / (1 + hop_distance)`
- Use `min(length(path))` to get shortest path when multiple paths exist
- Always set `retrieval_method = "graph"`

## Index Creation

Create indexes during service initialization (idempotent):

```cypher
CREATE INDEX IF NOT EXISTS FOR (e:LegalEntity) ON (e.entity_type)
```

```cypher
CREATE INDEX IF NOT EXISTS FOR (e:LegalEntity) ON (e.source_chunk_id)
```

Run these in the `initialize()` method during app lifespan startup.

## Single-Transaction Deletion Pattern

Delete all entities for a document in one transaction to ensure atomicity:

```cypher
MATCH (e:LegalEntity)
WHERE e.source_chunk_id STARTS WITH $document_id_prefix
DETACH DELETE e
```

`DETACH DELETE` removes the node and all connected relationships. This ensures no orphan relationships remain.

Alternative with explicit chunk ID list:

```cypher
UNWIND $chunk_ids AS chunk_id
MATCH (e:LegalEntity {source_chunk_id: chunk_id})
DETACH DELETE e
```

## Connection Pool Configuration

```python
from neo4j import AsyncGraphDatabase

driver = AsyncGraphDatabase.driver(
    uri=settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
    max_connection_pool_size=50,      # Max 50 connections
    connection_acquisition_timeout=5,  # 5s to acquire a connection
)
```

Pool sizing guidance:
- Minimum: 10 connections (low-traffic dev)
- Maximum: 50 connections (high concurrency)
- Each query acquires one connection from the pool
- Connection pool is shared across all async tasks

## Timeout Enforcement

All queries must complete within 5 seconds:

```python
async def execute_query(self, query: str, params: dict) -> list:
    async with self.driver.session(database=self.database) as session:
        result = await session.run(
            query,
            params,
            timeout=5.0,  # 5-second query timeout
        )
        return [record.data() async for record in result]
```

If the timeout is exceeded, catch `neo4j.exceptions.ClientError` or `asyncio.TimeoutError` and raise `GraphStoreUnavailableError`.

## Error Handling

```python
from neo4j.exceptions import ServiceUnavailable, SessionExpired, ClientError

try:
    result = await session.run(query, params, timeout=5.0)
except (ServiceUnavailable, SessionExpired) as e:
    logger.error("neo4j_unavailable", operation=operation, error=str(e))
    raise GraphStoreUnavailableError(f"Neo4j unavailable: {e}")
except ClientError as e:
    if "transaction has been terminated" in str(e):
        logger.error("neo4j_timeout", operation=operation, query=query[:100])
        raise GraphStoreUnavailableError(f"Query timeout: {e}")
    raise
```

## Query Parameterization

Never interpolate strings into Cypher queries. Always use `$param` syntax:

```python
# GOOD
await session.run("MATCH (e:LegalEntity {id: $id}) RETURN e", {"id": entity_id})

# BAD — SQL/Cypher injection risk
await session.run(f"MATCH (e:LegalEntity {{id: '{entity_id}'}}) RETURN e")
```

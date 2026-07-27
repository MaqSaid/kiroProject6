"""Property tests for Graph Service.

# Feature: legislation-rag-platform, Property 1: Entity storage round-trip preserves all data
# Feature: legislation-rag-platform, Property 2: Relationship storage with deduplication
# Feature: legislation-rag-platform, Property 3: Referential integrity on relationship storage
# Feature: legislation-rag-platform, Property 4: Graph traversal scoring follows distance formula
# Feature: legislation-rag-platform, Property 5: Document deletion removes exactly target document's data
# Feature: legislation-rag-platform, Property 28: Graph Service request body validation
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, ".")

from domain_models import ExtractedEntity, ExtractedRelationship
from domain_models.enums import LegalEntityType, LegalRelationshipType

from tests.fakes.fake_graph_store import FakeGraphStore


# --- Strategies ---

safe_text = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
)

json_value = st.one_of(
    st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters="\x00")),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    st.booleans(),
)

properties_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")),
    values=json_value,
    max_size=5,
)


@st.composite
def extracted_entity_strategy(draw, entity_id=None, source_chunk_id=None):
    """Generate a valid ExtractedEntity with random data."""
    eid = entity_id or draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")))
    name = draw(safe_text)
    entity_type = draw(st.sampled_from(list(LegalEntityType)))
    description = draw(safe_text)
    s_chunk_id = source_chunk_id or draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")))
    props = draw(properties_strategy)

    return ExtractedEntity(
        id=eid,
        name=name,
        entity_type=entity_type,
        description=description,
        source_chunk_id=s_chunk_id,
        properties=props,
    )


@st.composite
def extracted_entity_list_strategy(draw, min_size=1, max_size=10):
    """Generate a list of unique ExtractedEntity objects (unique by id)."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    ids = draw(
        st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    entities = []
    for eid in ids:
        entity = draw(extracted_entity_strategy(entity_id=eid))
        entities.append(entity)
    return entities


@st.composite
def extracted_relationship_strategy(
    draw,
    rel_id=None,
    source_entity_id=None,
    target_entity_id=None,
):
    """Generate a valid ExtractedRelationship."""
    rid = rel_id or draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")))
    src_id = source_entity_id or draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")))
    tgt_id = target_entity_id or draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_characters="\x00")))
    rel_type = draw(st.sampled_from(list(LegalRelationshipType)))
    description = draw(safe_text)
    props = draw(properties_strategy)

    return ExtractedRelationship(
        id=rid,
        source_entity_id=src_id,
        target_entity_id=tgt_id,
        relationship_type=rel_type,
        description=description,
        properties=props,
    )


# --- Helper ---

def run_async(coro):
    """Run an async coroutine synchronously for use in hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- Property 1: Entity storage round-trip preserves all data ---


@pytest.mark.property
@settings(max_examples=100)
@given(entities=extracted_entity_list_strategy(min_size=1, max_size=8))
def test_property_1_entity_storage_roundtrip(entities):
    """Property 1: Entity storage round-trip preserves all data.

    For any list of valid ExtractedEntity objects, storing via store_entities
    and then reading back by id returns results with all original properties.

    **Validates: Requirements 1.1, 1.9**
    """
    store = FakeGraphStore()
    stored_count = run_async(store.store_entities(entities))

    assert stored_count == len(entities)

    for entity in entities:
        stored = store.get_entity(entity.id)
        assert stored is not None, f"Entity {entity.id} not found after storage"
        assert stored["id"] == entity.id
        assert stored["name"] == entity.name
        assert stored["entity_type"] == entity.entity_type.value
        assert stored["description"] == entity.description
        assert stored["source_chunk_id"] == entity.source_chunk_id
        assert stored["properties"] == entity.properties


# --- Property 2: Relationship storage with deduplication ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    entity_a=extracted_entity_strategy(entity_id="ent-a"),
    entity_b=extracted_entity_strategy(entity_id="ent-b"),
    rel=extracted_relationship_strategy(
        rel_id="rel-1",
        source_entity_id="ent-a",
        target_entity_id="ent-b",
    ),
)
def test_property_2_relationship_deduplication(entity_a, entity_b, rel):
    """Property 2: Relationship storage with deduplication.

    Storing the same relationship id twice creates exactly one edge.

    **Validates: Requirements 1.2**
    """
    store = FakeGraphStore()
    run_async(store.store_entities([entity_a, entity_b]))

    # Store the same relationship twice
    run_async(store.store_relationships([rel]))
    run_async(store.store_relationships([rel]))

    # Should have exactly one relationship
    assert store.relationship_count == 1
    stored_rel = store.get_relationship(rel.id)
    assert stored_rel is not None
    assert stored_rel["source_entity_id"] == rel.source_entity_id
    assert stored_rel["target_entity_id"] == rel.target_entity_id


# --- Property 3: Referential integrity on relationship storage ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    entity=extracted_entity_strategy(entity_id="existing-ent"),
    rel_missing_source=extracted_relationship_strategy(
        source_entity_id="nonexistent-src",
        target_entity_id="existing-ent",
    ),
    rel_missing_target=extracted_relationship_strategy(
        source_entity_id="existing-ent",
        target_entity_id="nonexistent-tgt",
    ),
)
def test_property_3_referential_integrity(entity, rel_missing_source, rel_missing_target):
    """Property 3: Referential integrity on relationship storage.

    Relationships referencing non-existent entities are skipped.

    **Validates: Requirements 1.3**
    """
    store = FakeGraphStore()
    run_async(store.store_entities([entity]))

    # Relationship with missing source should be skipped
    stored_1, skipped_1 = run_async(store.store_relationships([rel_missing_source]))
    assert stored_1 == 0
    assert skipped_1 == 1

    # Relationship with missing target should be skipped
    stored_2, skipped_2 = run_async(store.store_relationships([rel_missing_target]))
    assert stored_2 == 0
    assert skipped_2 == 1

    # No relationships should exist in store
    assert store.relationship_count == 0


# --- Property 4: Graph traversal scoring follows distance formula ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    chain_length=st.integers(min_value=2, max_value=5),
    max_hops=st.integers(min_value=1, max_value=10),
)
def test_property_4_traversal_scoring_distance_formula(chain_length, max_hops):
    """Property 4: Graph traversal scoring follows distance formula.

    Score equals 1.0/(1+hop_distance), max_hops capped at 5.

    **Validates: Requirements 1.4, 14.4**
    """
    store = FakeGraphStore()

    # Build a chain of entities: e0 -> e1 -> e2 -> ... -> e(chain_length-1)
    # The start node (e0) has a name we can query for
    entities = []
    for i in range(chain_length):
        entity = ExtractedEntity(
            id=f"chain-ent-{i}",
            name=f"StartNode" if i == 0 else f"Node{i}",
            entity_type=LegalEntityType.SECTION,
            description=f"Description for node {i}",
            source_chunk_id=f"doc1-chunk-{i}",
            properties={},
        )
        entities.append(entity)

    run_async(store.store_entities(entities))

    # Create chain of relationships
    relationships = []
    for i in range(chain_length - 1):
        rel = ExtractedRelationship(
            id=f"chain-rel-{i}",
            source_entity_id=f"chain-ent-{i}",
            target_entity_id=f"chain-ent-{i+1}",
            relationship_type=LegalRelationshipType.CONTAINS,
            description=f"Connects {i} to {i+1}",
            properties={},
        )
        relationships.append(rel)

    run_async(store.store_relationships(relationships))

    # Traverse from "StartNode" query
    results = run_async(store.traverse("StartNode", max_hops=max_hops))

    # max_hops is capped at 5
    effective_max_hops = min(max_hops, 5)

    # Expected reachable nodes: those within effective_max_hops hops from start
    expected_reachable = min(chain_length - 1, effective_max_hops)

    assert len(results) == expected_reachable

    # Verify scoring formula for each result
    for result in results:
        assert result.retrieval_method == "graph"
        # Find the hop distance from entity id
        node_index = int(result.chunk_id.split("-")[-1])
        hop_distance = node_index  # distance from e0
        expected_score = 1.0 / (1 + hop_distance)
        assert abs(result.score - expected_score) < 1e-9, (
            f"Expected score {expected_score} for hop_distance={hop_distance}, "
            f"got {result.score}"
        )


# --- Property 5: Document deletion removes exactly target document's data ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    doc_a_count=st.integers(min_value=1, max_value=5),
    doc_b_count=st.integers(min_value=1, max_value=5),
)
def test_property_5_document_deletion_isolation(doc_a_count, doc_b_count):
    """Property 5: Document deletion removes exactly target document's data.

    DELETE /documents/{id} removes only that document's entities and relationships,
    leaving other documents' data unchanged.

    **Validates: Requirements 1.5**
    """
    store = FakeGraphStore()

    # Create entities for document A
    doc_a_entities = []
    for i in range(doc_a_count):
        entity = ExtractedEntity(
            id=f"docA-ent-{i}",
            name=f"DocA Entity {i}",
            entity_type=LegalEntityType.ACT,
            description=f"Doc A entity {i}",
            source_chunk_id=f"docA-chunk-{i}",
            properties={"doc": "A"},
        )
        doc_a_entities.append(entity)

    # Create entities for document B
    doc_b_entities = []
    for i in range(doc_b_count):
        entity = ExtractedEntity(
            id=f"docB-ent-{i}",
            name=f"DocB Entity {i}",
            entity_type=LegalEntityType.REGULATION,
            description=f"Doc B entity {i}",
            source_chunk_id=f"docB-chunk-{i}",
            properties={"doc": "B"},
        )
        doc_b_entities.append(entity)

    run_async(store.store_entities(doc_a_entities + doc_b_entities))

    # Create some relationships within doc A
    doc_a_rels = []
    if doc_a_count >= 2:
        for i in range(doc_a_count - 1):
            rel = ExtractedRelationship(
                id=f"docA-rel-{i}",
                source_entity_id=f"docA-ent-{i}",
                target_entity_id=f"docA-ent-{i+1}",
                relationship_type=LegalRelationshipType.CONTAINS,
                description="Within doc A",
                properties={},
            )
            doc_a_rels.append(rel)
        run_async(store.store_relationships(doc_a_rels))

    # Create some relationships within doc B
    doc_b_rels = []
    if doc_b_count >= 2:
        for i in range(doc_b_count - 1):
            rel = ExtractedRelationship(
                id=f"docB-rel-{i}",
                source_entity_id=f"docB-ent-{i}",
                target_entity_id=f"docB-ent-{i+1}",
                relationship_type=LegalRelationshipType.REFERENCES,
                description="Within doc B",
                properties={},
            )
            doc_b_rels.append(rel)
        run_async(store.store_relationships(doc_b_rels))

    # Delete document A
    deleted_nodes, deleted_rels = run_async(store.delete_by_document("docA"))

    # Verify doc A entities are gone
    assert deleted_nodes == doc_a_count
    for i in range(doc_a_count):
        assert store.get_entity(f"docA-ent-{i}") is None

    # Verify doc B entities remain intact
    for i in range(doc_b_count):
        stored = store.get_entity(f"docB-ent-{i}")
        assert stored is not None
        assert stored["source_chunk_id"] == f"docB-chunk-{i}"
        assert stored["properties"] == {"doc": "B"}

    # Verify doc B relationships remain
    expected_b_rels = max(0, doc_b_count - 1)
    remaining_rels = store.relationship_count
    assert remaining_rels == expected_b_rels


# --- Property 28: Graph Service request body validation ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    invalid_entity_type=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L",)),
    ).filter(lambda x: x not in [e.value for e in LegalEntityType]),
)
def test_property_28_invalid_entity_type_422(invalid_entity_type):
    """Property 28: Graph Service request body validation.

    Malformed bodies receive HTTP 422 with validation details.
    Specifically, invalid entity_type enum values should be rejected.

    **Validates: Requirements 14.3, 14.6**
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes import router

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.graph_store = FakeGraphStore()
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/entities",
            json={
                "entities": [
                    {
                        "id": "test-ent",
                        "name": "Test",
                        "entity_type": invalid_entity_type,
                        "description": "Test entity",
                        "source_chunk_id": "chunk-1",
                        "properties": {},
                    }
                ]
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    invalid_rel_type=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L",)),
    ).filter(lambda x: x not in [r.value for r in LegalRelationshipType]),
)
def test_property_28_invalid_relationship_type_422(invalid_rel_type):
    """Property 28: Graph Service request body validation.

    Invalid relationship_type enum values should receive HTTP 422.

    **Validates: Requirements 14.3, 14.6**
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes import router

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.graph_store = FakeGraphStore()
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/relationships",
            json={
                "relationships": [
                    {
                        "id": "rel-1",
                        "source_entity_id": "ent-1",
                        "target_entity_id": "ent-2",
                        "relationship_type": invalid_rel_type,
                        "description": "Test relationship",
                        "properties": {},
                    }
                ]
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@pytest.mark.property
@settings(max_examples=50, deadline=None)
@given(max_hops=st.integers(min_value=6, max_value=100))
def test_property_28_traverse_max_hops_exceeds_limit_422(max_hops):
    """Property 28: Graph Service request body validation.

    Traverse with max_hops > 5 should be rejected with HTTP 422
    (model has le=5 constraint).

    **Validates: Requirements 14.3, 14.6**
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes import router

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.graph_store = FakeGraphStore()
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/traverse",
            json={"query": "test query", "max_hops": max_hops},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@pytest.mark.property
@settings(max_examples=50, deadline=None)
@given(st.data())
def test_property_28_empty_entities_list_422(data):
    """Property 28: Graph Service request body validation.

    Empty entities list should receive HTTP 422 (min_length=1 on model).

    **Validates: Requirements 14.3, 14.6**
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes import router

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.graph_store = FakeGraphStore()
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/entities",
            json={"entities": []},
        )
        assert response.status_code == 422

        response = client.post(
            "/relationships",
            json={"relationships": []},
        )
        assert response.status_code == 422

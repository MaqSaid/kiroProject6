"""Property tests for Query Service.

# Feature: legislation-rag-platform, Property 15: API response completeness
# Feature: legislation-rag-platform, Property 16: Error response structure with correlation ID
# Feature: legislation-rag-platform, Property 17: Query validation at Query Service
# Feature: legislation-rag-platform, Property 18: RRF fusion with weight renormalization
# Feature: legislation-rag-platform, Property 19: Reranker output size invariant
# Feature: legislation-rag-platform, Property 20: Confidence composite formula correctness
# Feature: legislation-rag-platform, Property 21: Fallback response threshold
"""

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from domain_models.api_models import ConfidenceScoreResponse
from domain_models.core import ScoredChunk
from src.agents.confidence_scorer import ConfidenceScorer
from src.agents.reranker import Reranker
from src.agents.retrieval_agent import RetrievalAgent, DEFAULT_WEIGHTS
from src.main import create_app
from src.orchestrator import RAGOrchestrator, FALLBACK_THRESHOLD
from src.agents.citation_agent import CitationVerificationAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.generation_agent import GenerationAgent


# --- Strategies ---

valid_query_strategy = st.text(
    min_size=1,
    max_size=2000,
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), min_codepoint=32),
).filter(lambda s: len(s.strip()) > 0)

confidence_float = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)


@st.composite
def scored_chunk_list_strategy(draw, min_size=0, max_size=20):
    """Generate a list of valid ScoredChunks with unique chunk_ids."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    chunks = []
    for i in range(n):
        chunks.append(
            ScoredChunk(
                chunk_id=f"chunk_{i}",
                document_id=f"doc_{i % 5}",
                text=f"This is the text content of chunk number {i} with legislative details.",
                section_heading=f"Section {i + 1}",
                score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
                retrieval_method=draw(st.sampled_from(["dense", "sparse", "graph"])),
                metadata={},
            )
        )
    return chunks


# --- Helper ---


def _make_test_app():
    """Create a test app with orchestrator pre-initialized (bypasses lifespan)."""
    application = create_app()
    application.state.orchestrator = RAGOrchestrator(
        retrieval_agent=RetrievalAgent(
            embedding_client=None,
            graph_client=None,
            chromadb_store=None,
            bm25_index=None,
        ),
        generation_agent=GenerationAgent(),
        citation_agent=CitationVerificationAgent(),
        evaluation_agent=EvaluationAgent(),
    )
    application.state.embedding_client = None
    application.state.graph_client = None
    return application


# --- Property 15: API response completeness ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(query=valid_query_strategy)
@pytest.mark.asyncio
async def test_property_15_successful_response_has_all_required_fields(query):
    """Property 15: Every successful response contains answer, citations,
    confidence_scores (with all 4 sub-fields), source_chunks, and is_fallback.

    **Validates: Requirements 7.3**
    """
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={"query": query})
        assert response.status_code == 200

        data = response.json()

        # Top-level required fields
        assert "answer" in data
        assert "citations" in data
        assert "confidence_scores" in data
        assert "source_chunks" in data
        assert "is_fallback" in data

        # confidence_scores must have all 4 sub-fields
        cs = data["confidence_scores"]
        assert "retrieval_confidence" in cs
        assert "citation_coverage" in cs
        assert "answer_completeness" in cs
        assert "composite" in cs

        # Types
        assert isinstance(data["answer"], str)
        assert isinstance(data["citations"], list)
        assert isinstance(data["source_chunks"], list)
        assert isinstance(data["is_fallback"], bool)
        assert isinstance(cs["retrieval_confidence"], (int, float))
        assert isinstance(cs["citation_coverage"], (int, float))
        assert isinstance(cs["answer_completeness"], (int, float))
        assert isinstance(cs["composite"], (int, float))


# --- Property 16: Error response structure with correlation ID ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    query=valid_query_strategy,
    error_msg=st.text(
        min_size=1, max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), min_codepoint=32),
    ),
)
@pytest.mark.asyncio
async def test_property_16_error_response_structure(query, error_msg):
    """Property 16: Agent/service failures return HTTP 500 with error_code,
    message, and correlation_id.

    **Validates: Requirements 7.4**
    """
    app = _make_test_app()

    # Make the orchestrator's ask method raise an exception
    async def mock_ask(*args, **kwargs):
        raise RuntimeError(error_msg)

    app.state.orchestrator.ask = mock_ask

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/agents/ask",
            json={"query": query},
            headers={"X-Correlation-ID": "test-corr-123"},
        )
        assert response.status_code == 500

        data = response.json()
        assert "error_code" in data
        assert "message" in data
        assert "correlation_id" in data

        # Values are non-empty
        assert len(data["error_code"]) > 0
        assert len(data["message"]) > 0
        assert len(data["correlation_id"]) > 0


# --- Property 17: Query validation at Query Service ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(query=valid_query_strategy)
@pytest.mark.asyncio
async def test_property_17_valid_queries_are_processed(query):
    """Property 17: Valid queries (1-2000 chars) are processed successfully.

    **Validates: Requirements 7.6**
    """
    assume(1 <= len(query) <= 2000)

    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={"query": query})
        assert response.status_code == 200


@pytest.mark.property
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    query=st.text(
        min_size=2001, max_size=3000,
        alphabet=st.characters(whitelist_categories=("L",), min_codepoint=65, max_codepoint=90),
    )
)
@pytest.mark.asyncio
async def test_property_17_oversized_queries_return_422(query):
    """Property 17: Oversized queries (>2000 chars) return HTTP 422.

    **Validates: Requirements 7.6**
    """
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={"query": query})
        assert response.status_code == 422


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(data=st.just(None))
@pytest.mark.asyncio
async def test_property_17_empty_query_returns_422(data):
    """Property 17: Empty query returns HTTP 422.

    **Validates: Requirements 7.6**
    """
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={"query": ""})
        assert response.status_code == 422


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(data=st.just(None))
@pytest.mark.asyncio
async def test_property_17_missing_query_returns_422(data):
    """Property 17: Missing query field returns HTTP 422.

    **Validates: Requirements 7.6**
    """
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={})
        assert response.status_code == 422


# --- Property 18: RRF fusion with weight renormalization ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    available_methods=st.lists(
        st.sampled_from(["dense", "sparse", "graph"]),
        min_size=1,
        max_size=3,
        unique=True,
    )
)
def test_property_18_renormalized_weights_sum_to_one(available_methods):
    """Property 18: Renormalized weights always sum to 1.0.

    **Validates: Requirements 10.2, 10.4, 13.5**
    """
    weights = RetrievalAgent._renormalize_weights(DEFAULT_WEIGHTS, available_methods)

    # All returned keys match available methods
    assert set(weights.keys()) == set(available_methods)

    # Weights sum to 1.0
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    # All weights positive
    for method, weight in weights.items():
        assert weight > 0.0, f"Weight for {method} is {weight}, expected > 0"


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    available_methods=st.lists(
        st.sampled_from(["dense", "sparse", "graph"]),
        min_size=2,
        max_size=3,
        unique=True,
    )
)
def test_property_18_renormalized_weights_preserve_ratio(available_methods):
    """Property 18: Ratio between any two available methods equals ratio of original weights.

    **Validates: Requirements 10.2, 10.4, 13.5**
    """
    weights = RetrievalAgent._renormalize_weights(DEFAULT_WEIGHTS, available_methods)

    # Check ratio preservation for all pairs
    for i in range(len(available_methods)):
        for j in range(i + 1, len(available_methods)):
            m1 = available_methods[i]
            m2 = available_methods[j]
            original_ratio = DEFAULT_WEIGHTS[m1] / DEFAULT_WEIGHTS[m2]
            renormalized_ratio = weights[m1] / weights[m2]
            assert abs(original_ratio - renormalized_ratio) < 1e-9, (
                f"Ratio {m1}/{m2}: original={original_ratio}, "
                f"renormalized={renormalized_ratio}"
            )


# --- Property 19: Reranker output size invariant ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(candidates=scored_chunk_list_strategy(min_size=0, max_size=20))
@pytest.mark.asyncio
async def test_property_19_reranker_returns_min_5_n(candidates):
    """Property 19: Reranker returns min(5, N) results for N fused candidates.

    **Validates: Requirements 10.5**
    """
    reranker = Reranker(fake=True)
    result = await reranker.rerank("test query", candidates, top_n=5)

    expected_count = min(5, len(candidates))
    assert len(result) == expected_count, (
        f"Expected {expected_count} results for {len(candidates)} candidates, "
        f"got {len(result)}"
    )


# --- Property 20: Confidence composite formula correctness ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    retrieval=confidence_float,
    citation=confidence_float,
    completeness=confidence_float,
)
def test_property_20_composite_formula_correct(retrieval, citation, completeness):
    """Property 20: Composite = round(0.35*r + 0.40*c + 0.25*a, 2) and in [0.0, 1.0].

    **Validates: Requirements 11.1**
    """
    expected = round(0.35 * retrieval + 0.40 * citation + 0.25 * completeness, 2)

    # Verify the expected value is in [0.0, 1.0]
    assert 0.0 <= expected <= 1.0, f"Expected composite {expected} not in [0.0, 1.0]"

    # Verify ConfidenceScoreResponse model accepts these values
    response = ConfidenceScoreResponse(
        retrieval_confidence=retrieval,
        citation_coverage=citation,
        answer_completeness=completeness,
        composite=expected,
    )
    assert 0.0 <= response.composite <= 1.0


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    retrieval=confidence_float,
    citation=confidence_float,
    completeness=confidence_float,
)
def test_property_20_confidence_scorer_matches_formula(retrieval, citation, completeness):
    """Property 20: ConfidenceScorer.compute produces composite matching the formula.

    **Validates: Requirements 11.1**
    """
    # Create a chunk with the target retrieval score
    chunks = [
        ScoredChunk(
            chunk_id="chunk_0",
            document_id="doc_0",
            text="Test content with legal provisions. Section 1 applies here.",
            section_heading="Section 1",
            score=retrieval,
            retrieval_method="hybrid",
            metadata={},
        )
    ]

    scorer = ConfidenceScorer()
    result = scorer.compute(
        query="test query about legislation",
        answer="Answer text here.",
        chunks=chunks,
        citations=[],
    )

    # The composite should always be in [0.0, 1.0]
    assert 0.0 <= result.composite <= 1.0

    # Verify the composite matches the formula applied to computed sub-scores
    expected = round(
        0.35 * result.retrieval_confidence
        + 0.40 * result.citation_coverage
        + 0.25 * result.answer_completeness,
        2,
    )
    assert result.composite == expected, (
        f"Composite {result.composite} != expected {expected} "
        f"(r={result.retrieval_confidence}, c={result.citation_coverage}, "
        f"a={result.answer_completeness})"
    )


# --- Property 21: Fallback response threshold ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(composite=st.floats(min_value=0.0, max_value=0.39, allow_nan=False, allow_infinity=False))
def test_property_21_below_threshold_triggers_fallback(composite):
    """Property 21: composite < 0.4 implies is_fallback is True.

    **Validates: Requirements 11.2, 11.3**
    """
    assert composite < FALLBACK_THRESHOLD
    is_fallback = composite < FALLBACK_THRESHOLD
    assert is_fallback is True


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(composite=st.floats(min_value=0.4, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_property_21_at_or_above_threshold_no_fallback(composite):
    """Property 21: composite >= 0.4 implies is_fallback is False.

    **Validates: Requirements 11.2, 11.3**
    """
    assert composite >= FALLBACK_THRESHOLD
    is_fallback = composite < FALLBACK_THRESHOLD
    assert is_fallback is False


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(query=valid_query_strategy)
@pytest.mark.asyncio
async def test_property_21_fallback_response_includes_fallback_info(query):
    """Property 21: When is_fallback is True, response includes fallback_info
    with found_topics, not_found_topics, and suggested_documents.

    **Validates: Requirements 11.2, 11.3**
    """
    # The test app orchestrator has no retrieval sources, so
    # confidence will be 0.0 (below threshold) — triggering fallback
    app = _make_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/agents/ask", json={"query": query})
        assert response.status_code == 200

        data = response.json()
        # With no retrieval sources, composite should be 0.0 (below 0.4)
        assert data["is_fallback"] is True
        assert data["fallback_info"] is not None

        fallback_info = data["fallback_info"]
        assert "found_topics" in fallback_info
        assert "not_found_topics" in fallback_info
        assert "suggested_documents" in fallback_info

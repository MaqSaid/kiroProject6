"""Unit tests for Query Service endpoints.

Tests cover:
- Query validation (empty → 422, oversized → 422)
- Successful ask returns valid AgentAskResponse shape
- Error handling returns ErrorResponse with correlation_id
- Health endpoints
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.citation_agent import CitationVerificationAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.generation_agent import GenerationAgent
from src.agents.retrieval_agent import RetrievalAgent
from src.main import create_app
from src.orchestrator import RAGOrchestrator


@pytest.fixture
def app():
    """Create a fresh app with orchestrator pre-initialized (bypassing lifespan)."""
    application = create_app()
    # Manually initialize app state to avoid needing lifespan in tests
    application.state.orchestrator = RAGOrchestrator(
        retrieval_agent=RetrievalAgent(),
        generation_agent=GenerationAgent(),
        citation_agent=CitationVerificationAgent(),
        evaluation_agent=EvaluationAgent(),
    )
    application.state.embedding_client = None
    application.state.graph_client = None
    return application


@pytest.fixture
async def client(app):
    """Create an async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_agents_ask_empty_query_returns_422(client: AsyncClient):
    """Empty query field should return HTTP 422."""
    response = await client.post("/v1/agents/ask", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agents_ask_missing_query_returns_422(client: AsyncClient):
    """Missing query field should return HTTP 422."""
    response = await client.post("/v1/agents/ask", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agents_ask_oversized_query_returns_422(client: AsyncClient):
    """Query exceeding 2000 characters should return HTTP 422."""
    long_query = "a" * 2001
    response = await client.post("/v1/agents/ask", json={"query": long_query})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agents_ask_max_length_accepted(client: AsyncClient):
    """Query at exactly 2000 characters should be accepted."""
    query = "a" * 2000
    response = await client.post("/v1/agents/ask", json={"query": query})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agents_ask_valid_query_returns_response_shape(client: AsyncClient):
    """Valid query should return AgentAskResponse with all required fields."""
    response = await client.post(
        "/v1/agents/ask",
        json={"query": "What are the road design standards?"},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify all required fields present
    assert "answer" in data
    assert "citations" in data
    assert "confidence_scores" in data
    assert "source_chunks" in data
    assert "is_fallback" in data

    # Verify confidence_scores shape
    scores = data["confidence_scores"]
    assert "retrieval_confidence" in scores
    assert "citation_coverage" in scores
    assert "answer_completeness" in scores
    assert "composite" in scores

    # Verify types
    assert isinstance(data["answer"], str)
    assert isinstance(data["citations"], list)
    assert isinstance(data["source_chunks"], list)
    assert isinstance(data["is_fallback"], bool)


@pytest.mark.asyncio
async def test_agents_ask_includes_correlation_id_header(client: AsyncClient):
    """Response should include X-Correlation-ID header."""
    response = await client.post(
        "/v1/agents/ask",
        json={"query": "Test query"},
        headers={"X-Correlation-ID": "test-corr-123"},
    )
    assert response.status_code == 200
    assert "x-correlation-id" in response.headers
    assert response.headers["x-correlation-id"] == "test-corr-123"


@pytest.mark.asyncio
async def test_direct_ask_empty_query_returns_422(client: AsyncClient):
    """Empty query on /v1/ask should return HTTP 422."""
    response = await client.post("/v1/ask", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_direct_ask_valid_query_returns_response(client: AsyncClient):
    """Valid query on /v1/ask should return valid response."""
    response = await client.post(
        "/v1/ask",
        json={"query": "What penalties exist for exceeding weight limits?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "confidence_scores" in data
    assert "is_fallback" in data


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Health endpoint should return healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "query-service"


@pytest.mark.asyncio
async def test_health_live_endpoint(client: AsyncClient):
    """Liveness probe should always return 200."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_health_ready_endpoint(client: AsyncClient):
    """Readiness probe should check dependencies."""
    response = await client.get("/health/ready")
    # Orchestrator is initialized but clients are None in test mode
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert data["checks"]["orchestrator"] == "ready"


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    """Metrics endpoint should return Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text or "orchestrator_ask_duration" in response.text


@pytest.mark.asyncio
async def test_error_response_includes_correlation_id():
    """When orchestrator raises, response should include error_code, message, correlation_id."""
    from unittest.mock import AsyncMock, patch

    application = create_app()
    mock_orchestrator = RAGOrchestrator(
        retrieval_agent=RetrievalAgent(),
        generation_agent=GenerationAgent(),
        citation_agent=CitationVerificationAgent(),
        evaluation_agent=EvaluationAgent(),
    )
    application.state.orchestrator = mock_orchestrator
    application.state.embedding_client = None
    application.state.graph_client = None

    # Patch the orchestrator's ask method to raise
    with patch.object(mock_orchestrator, "ask", new_callable=AsyncMock) as mock_ask:
        mock_ask.side_effect = RuntimeError("Generation Agent timeout")

        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as ac:
            response = await ac.post(
                "/v1/agents/ask",
                json={"query": "Test query for error handling"},
                headers={"X-Correlation-ID": "err-corr-456"},
            )

    assert response.status_code == 500
    data = response.json()
    assert "error_code" in data
    assert "message" in data
    assert "correlation_id" in data
    assert data["correlation_id"] == "err-corr-456"
    assert "RUNTIMEERROR" in data["error_code"]

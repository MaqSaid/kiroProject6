"""Shared test fixtures for Query Service tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.citation_agent import CitationVerificationAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.generation_agent import GenerationAgent
from src.agents.prompt_loader import load_prompt
from src.agents.retrieval_agent import RetrievalAgent
from src.main import create_app
from src.orchestrator import RAGOrchestrator


@pytest.fixture
def app():
    """Create a test application with orchestrator pre-initialized."""
    application = create_app()
    # RetrievalAgent with no dependencies returns empty results (graceful)
    application.state.orchestrator = RAGOrchestrator(
        retrieval_agent=RetrievalAgent(
            embedding_client=None,
            graph_client=None,
            chromadb_store=None,
            bm25_index=None,
            system_prompt=load_prompt("retrieval_agent"),
        ),
        generation_agent=GenerationAgent(
            system_prompt=load_prompt("generation_agent"),
        ),
        citation_agent=CitationVerificationAgent(
            system_prompt=load_prompt("citation_verification_agent"),
        ),
        evaluation_agent=EvaluationAgent(
            system_prompt=load_prompt("evaluation_agent"),
        ),
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

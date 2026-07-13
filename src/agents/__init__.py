"""Strands-based AI agents for the RAG pipeline.

This package contains specialized agents that handle the intelligent
orchestration of retrieval, generation, citation verification, ingestion,
and evaluation tasks using the Strands Agents SDK.

Each agent wraps domain port operations as Strands tools, allowing the
underlying LLM to reason about which operations to perform and in what order.
"""

from src.agents.citation_verification_agent import create_citation_verification_agent
from src.agents.evaluation_agent import create_evaluation_agent
from src.agents.generation_agent import create_generation_agent
from src.agents.ingestion_agent import create_ingestion_agent
from src.agents.retrieval_agent import create_retrieval_agent

__all__ = [
    "create_citation_verification_agent",
    "create_evaluation_agent",
    "create_generation_agent",
    "create_ingestion_agent",
    "create_retrieval_agent",
]

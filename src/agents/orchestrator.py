"""RAG Pipeline Orchestrator — coordinates all agents for end-to-end operations.

This module provides the high-level orchestration that wires agents together
for complete RAG operations (ask, ingest, evaluate). It manages the agent
lifecycle and passes results between agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from src.agents.base import AgentConfig, get_default_config
from src.agents.citation_verification_agent import create_citation_verification_agent
from src.agents.evaluation_agent import create_evaluation_agent
from src.agents.generation_agent import create_generation_agent
from src.agents.ingestion_agent import create_ingestion_agent
from src.agents.retrieval_agent import create_retrieval_agent
from src.domain.events.bus import EventBus
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.normalizer import DocumentNormalizer
from src.ports.document_store import DocumentStorePort
from src.ports.embedding import EmbeddingPort
from src.ports.graph_store import GraphStorePort
from src.ports.reranker import RerankerPort
from src.ports.sparse_index import SparseIndexPort
from src.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)


@dataclass
class AskResult:
    """Result of an end-to-end ask operation through the agent pipeline."""

    answer: str
    citations: list[dict[str, Any]]
    confidence: dict[str, Any]
    verification: dict[str, Any]
    retrieval_info: dict[str, Any]
    is_fallback: bool = False
    correlation_id: str = ""


@dataclass
class IngestResult:
    """Result of an end-to-end ingestion operation."""

    document_id: str
    chunks_produced: int
    entities_extracted: int
    duplicates_found: int
    status: str
    details: dict[str, Any]
    correlation_id: str = ""


class RAGOrchestrator:
    """Coordinates all RAG pipeline agents for end-to-end operations.

    This orchestrator creates and manages the lifecycle of:
    - Retrieval Agent (hybrid search)
    - Generation Agent (grounded answers)
    - Citation Verification Agent (faithfulness checks)
    - Ingestion Agent (document processing)
    - Evaluation Agent (quality benchmarking)

    Usage:
        orchestrator = RAGOrchestrator(
            embedding_port=embedding,
            vector_store=vector_store,
            sparse_index=sparse_index,
            graph_store=graph_store,
            reranker=reranker,
            document_store=document_store,
            normalizer=normalizer,
            chunker_factory=chunker_factory,
            event_bus=event_bus,
        )

        # Ask a question
        result = orchestrator.ask("What is the deployment process?")

        # Ingest a document
        result = orchestrator.ingest("document-uuid-here")

        # Run evaluation
        result = orchestrator.evaluate("path/to/golden_dataset.json")
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_store: VectorStorePort,
        sparse_index: SparseIndexPort,
        graph_store: GraphStorePort,
        reranker: RerankerPort,
        document_store: DocumentStorePort,
        normalizer: DocumentNormalizer,
        chunker_factory: ChunkerFactory,
        event_bus: EventBus,
        config: AgentConfig | None = None,
    ) -> None:
        self._config = config or get_default_config()

        # Store ports for agent creation
        self._embedding_port = embedding_port
        self._vector_store = vector_store
        self._sparse_index = sparse_index
        self._graph_store = graph_store
        self._reranker = reranker
        self._document_store = document_store
        self._normalizer = normalizer
        self._chunker_factory = chunker_factory
        self._event_bus = event_bus

        # Lazy agent initialization
        self._retrieval_agent = None
        self._generation_agent = None
        self._verification_agent = None
        self._ingestion_agent = None
        self._evaluation_agent = None

        logger.info("rag_orchestrator.initialized")

    @property
    def retrieval_agent(self):
        """Lazy-load the retrieval agent."""
        if self._retrieval_agent is None:
            self._retrieval_agent = create_retrieval_agent(
                embedding_port=self._embedding_port,
                vector_store=self._vector_store,
                sparse_index=self._sparse_index,
                graph_store=self._graph_store,
                reranker=self._reranker,
                config=self._config,
            )
        return self._retrieval_agent

    @property
    def generation_agent(self):
        """Lazy-load the generation agent."""
        if self._generation_agent is None:
            self._generation_agent = create_generation_agent(config=self._config)
        return self._generation_agent

    @property
    def verification_agent(self):
        """Lazy-load the citation verification agent."""
        if self._verification_agent is None:
            self._verification_agent = create_citation_verification_agent(
                config=self._config
            )
        return self._verification_agent

    @property
    def ingestion_agent(self):
        """Lazy-load the ingestion agent."""
        if self._ingestion_agent is None:
            self._ingestion_agent = create_ingestion_agent(
                document_store=self._document_store,
                normalizer=self._normalizer,
                chunker_factory=self._chunker_factory,
                embedding_port=self._embedding_port,
                vector_store=self._vector_store,
                sparse_index=self._sparse_index,
                graph_store=self._graph_store,
                event_bus=self._event_bus,
                config=self._config,
            )
        return self._ingestion_agent

    @property
    def evaluation_agent(self):
        """Lazy-load the evaluation agent."""
        if self._evaluation_agent is None:
            self._evaluation_agent = create_evaluation_agent(config=self._config)
        return self._evaluation_agent

    def ask(self, query: str, correlation_id: str = "") -> str:
        """Execute the full ask pipeline: retrieve → generate → verify.

        Coordinates the Retrieval Agent, Generation Agent, and Citation
        Verification Agent to produce a grounded, verified answer.

        Args:
            query: The user's question.
            correlation_id: Request correlation ID for tracing.

        Returns:
            The agent's response as a string (includes answer, citations, confidence).
        """
        import uuid

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        logger.info(
            "orchestrator.ask.start",
            query=query[:100],
            correlation_id=correlation_id,
        )

        # Step 1: Retrieve relevant chunks
        retrieval_prompt = (
            f"Find the most relevant document chunks for this query: {query}\n"
            f"Use all available search methods (dense, sparse, graph) and return "
            f"the top 5 reranked results."
        )
        retrieval_response = self.retrieval_agent(retrieval_prompt)

        # Step 2: Generate grounded answer
        generation_prompt = (
            f"Generate a grounded answer with citations for the query: {query}\n\n"
            f"Retrieved context:\n{retrieval_response!s}\n\n"
            f"Follow the complete generation workflow: format context, generate "
            f"answer, extract citations, compute confidence. If confidence is "
            f"below 0.4, use the fallback response."
        )
        generation_response = self.generation_agent(generation_prompt)

        # Step 3: Verify citations
        verification_prompt = (
            f"Verify the citations in this answer:\n\n"
            f"Answer: {generation_response!s}\n\n"
            f"Context used: {retrieval_response!s}\n\n"
            f"Check each citation-claim pair and produce a verification report."
        )
        verification_response = self.verification_agent(verification_prompt)

        logger.info(
            "orchestrator.ask.complete",
            correlation_id=correlation_id,
            query=query[:100],
        )

        # Combine into final response
        final = (
            f"## Answer\n\n{generation_response!s}\n\n"
            f"## Verification\n\n{verification_response!s}"
        )

        return final

    def ingest(self, document_id: str, correlation_id: str = "") -> str:
        """Execute the full ingestion pipeline for a document.

        Coordinates the Ingestion Agent to process a document through:
        validate → normalize → chunk → deduplicate → index → extract → emit event.

        Args:
            document_id: UUID of the uploaded document.
            correlation_id: Request correlation ID for tracing.

        Returns:
            The agent's response (ingestion summary).
        """
        import uuid

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        logger.info(
            "orchestrator.ingest.start",
            document_id=document_id,
            correlation_id=correlation_id,
        )

        ingestion_prompt = (
            f"Process document {document_id} through the complete ingestion pipeline. "
            f"Execute all steps in order: validate, normalize, chunk, deduplicate, "
            f"index, extract entities, and emit the completion event. "
            f"Use the 'recursive' chunking strategy unless the document format "
            f"suggests otherwise. Report the final summary."
        )

        response = self.ingestion_agent(ingestion_prompt)

        logger.info(
            "orchestrator.ingest.complete",
            document_id=document_id,
            correlation_id=correlation_id,
        )

        return str(response)

    def evaluate(self, dataset_path: str, correlation_id: str = "") -> str:
        """Run evaluation against the golden dataset.

        Uses the Evaluation Agent to load the dataset, run each question
        through the pipeline, and compute aggregate quality metrics.

        Args:
            dataset_path: Path to the golden dataset JSON file.
            correlation_id: Request correlation ID for tracing.

        Returns:
            The evaluation summary report.
        """
        import uuid

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        logger.info(
            "orchestrator.evaluate.start",
            dataset_path=dataset_path,
            correlation_id=correlation_id,
        )

        evaluation_prompt = (
            f"Load the golden dataset from '{dataset_path}' and evaluate "
            f"the RAG pipeline quality. For each question in the dataset, "
            f"score correctness, faithfulness, retrieval relevance, and citation "
            f"accuracy. Then compute the overall summary with aggregate metrics "
            f"and identify the weakest areas."
        )

        response = self.evaluation_agent(evaluation_prompt)

        logger.info(
            "orchestrator.evaluate.complete",
            dataset_path=dataset_path,
            correlation_id=correlation_id,
        )

        return str(response)

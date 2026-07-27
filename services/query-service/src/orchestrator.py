"""RAGOrchestrator coordinating the agent pipeline for query processing."""

from __future__ import annotations

import structlog

from domain_models.api_models import (
    AgentAskResponse,
    ConfidenceScoreResponse,
    FallbackInfoResponse,
    SourceChunkResponse,
)
from src.agents.citation_agent import CitationVerificationAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.generation_agent import GenerationAgent
from src.agents.reranker import Reranker
from src.agents.retrieval_agent import RetrievalAgent
from src.sanitizer import sanitize_output

logger = structlog.get_logger(__name__)

FALLBACK_THRESHOLD = 0.4


class RAGOrchestrator:
    """Coordinates Retrieval, Generation, Citation Verification, and Evaluation agents.

    The orchestrator processes queries through the full agent pipeline:
    1. Retrieve (hybrid search: dense + sparse + graph)
    2. Rerank top 20 fused candidates to top 5
    3. Generate answer with citations
    4. Verify citations
    5. Compute confidence scores
    6. Sanitize output
    7. Check fallback threshold and build response
    """

    def __init__(
        self,
        retrieval_agent: RetrievalAgent,
        generation_agent: GenerationAgent,
        citation_agent: CitationVerificationAgent,
        evaluation_agent: EvaluationAgent,
        reranker: Reranker | None = None,
    ) -> None:
        self._retrieval_agent = retrieval_agent
        self._generation_agent = generation_agent
        self._citation_agent = citation_agent
        self._evaluation_agent = evaluation_agent
        self._reranker = reranker or Reranker(fake=True)

    async def ask(self, query: str, correlation_id: str) -> AgentAskResponse:
        """Process a query through the full agent pipeline.

        Args:
            query: The user's natural language query.
            correlation_id: Request correlation ID for tracing.

        Returns:
            Complete agent response with answer, citations, confidence, and sources.

        Raises:
            Exception: On agent or service failures (caught by error handler).
        """
        logger.info("orchestrator.ask.start", query=query[:100], correlation_id=correlation_id)

        # Step 1: Retrieve relevant chunks (up to 20 per method, fused via RRF)
        chunks = await self._retrieval_agent.retrieve(query, correlation_id)
        logger.info("orchestrator.retrieval.complete", chunk_count=len(chunks), correlation_id=correlation_id)

        # Step 2: Rerank top 20 fused candidates, return top 5
        reranked_chunks = await self._reranker.rerank(query, chunks[:20], top_n=5)
        logger.info(
            "orchestrator.rerank.complete",
            input_count=len(chunks),
            output_count=len(reranked_chunks),
            correlation_id=correlation_id,
        )

        # Step 3: Generate answer using reranked chunks
        raw_answer = await self._generation_agent.generate(query, reranked_chunks, correlation_id)
        logger.info("orchestrator.generation.complete", correlation_id=correlation_id)

        # Step 4: Verify citations
        citations = await self._citation_agent.verify(raw_answer, reranked_chunks, correlation_id)
        logger.info("orchestrator.citation.complete", citation_count=len(citations), correlation_id=correlation_id)

        # Step 5: Compute confidence scores
        confidence = await self._evaluation_agent.evaluate(
            query, raw_answer, reranked_chunks, citations, correlation_id
        )
        logger.info("orchestrator.evaluation.complete", composite=confidence.composite, correlation_id=correlation_id)

        # Step 6: Sanitize output
        answer = sanitize_output(raw_answer)

        # Step 7: Build response with fallback logic
        source_chunks = [
            SourceChunkResponse(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                section_heading=chunk.section_heading,
                score=chunk.score,
                retrieval_method=chunk.retrieval_method,
            )
            for chunk in reranked_chunks
        ]

        is_fallback = confidence.composite < FALLBACK_THRESHOLD
        fallback_info = None
        if is_fallback:
            fallback_info = self._build_fallback_info(query, reranked_chunks)

        response = AgentAskResponse(
            answer=answer,
            citations=citations,
            confidence_scores=confidence,
            source_chunks=source_chunks,
            is_fallback=is_fallback,
            fallback_info=fallback_info,
        )

        logger.info("orchestrator.ask.complete", is_fallback=is_fallback, correlation_id=correlation_id)
        return response

    async def direct_ask(self, query: str, correlation_id: str) -> AgentAskResponse:
        """Process a direct retrieval-only query (no full agent pipeline).

        Args:
            query: The user's natural language query.
            correlation_id: Request correlation ID for tracing.

        Returns:
            Response with retrieval results but without full citation verification.
        """
        logger.info("orchestrator.direct_ask.start", query=query[:100], correlation_id=correlation_id)

        # Only retrieval + basic answer generation (no citation verification or evaluation)
        chunks = await self._retrieval_agent.retrieve(query, correlation_id)
        raw_answer = await self._generation_agent.generate(query, chunks, correlation_id)
        answer = sanitize_output(raw_answer)

        source_chunks = [
            SourceChunkResponse(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                section_heading=chunk.section_heading,
                score=chunk.score,
                retrieval_method=chunk.retrieval_method,
            )
            for chunk in chunks
        ]

        # Default confidence for direct ask (no evaluation agent)
        confidence = ConfidenceScoreResponse(
            retrieval_confidence=0.0,
            citation_coverage=0.0,
            answer_completeness=0.0,
            composite=0.0,
        )

        is_fallback = confidence.composite < FALLBACK_THRESHOLD
        fallback_info = None
        if is_fallback:
            fallback_info = self._build_fallback_info(query, chunks)

        return AgentAskResponse(
            answer=answer,
            citations=[],
            confidence_scores=confidence,
            source_chunks=source_chunks,
            is_fallback=is_fallback,
            fallback_info=fallback_info,
        )

    def _build_fallback_info(
        self, query: str, chunks: list
    ) -> FallbackInfoResponse:
        """Build fallback response info with found/not-found topics and suggestions.

        Args:
            query: The original user query.
            chunks: Retrieved chunks (may be empty).

        Returns:
            FallbackInfoResponse with topics and suggested documents.
        """
        # Found topics: section headings from retrieved chunks (up to 5 unique)
        found_topics: list[str] = []
        seen_headings: set[str] = set()
        for chunk in chunks:
            heading = chunk.section_heading if hasattr(chunk, "section_heading") else ""
            if heading and heading not in seen_headings and len(found_topics) < 5:
                found_topics.append(heading)
                seen_headings.add(heading)

        # Not-found topics: query terms not found in any chunk text
        query_terms = [word.lower() for word in query.split() if len(word) > 3]
        chunk_texts_combined = " ".join(
            chunk.text.lower() for chunk in chunks if hasattr(chunk, "text")
        )
        not_found_topics = [
            term for term in query_terms if term not in chunk_texts_combined
        ]

        # Suggested documents: up to 3 unique document IDs from retrieved chunks ranked by score
        suggested_documents: list[str] = []
        seen_docs: set[str] = set()
        # Chunks should already be sorted by score (reranked), but sort to be safe
        sorted_chunks = sorted(
            chunks, key=lambda c: c.score if hasattr(c, "score") else 0.0, reverse=True
        )
        for chunk in sorted_chunks:
            doc_id = chunk.document_id if hasattr(chunk, "document_id") else ""
            if doc_id and doc_id not in seen_docs and len(suggested_documents) < 3:
                suggested_documents.append(doc_id)
                seen_docs.add(doc_id)

        return FallbackInfoResponse(
            found_topics=found_topics,
            not_found_topics=not_found_topics,
            suggested_documents=suggested_documents,
        )

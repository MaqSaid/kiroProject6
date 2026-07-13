"""Generation Service — produces grounded answers with citations using Strands Agent.

Takes retrieved chunks and a query, generates an answer grounded in context,
includes bracketed citation references, and computes confidence scores.
Uses Amazon Bedrock via Strands for LLM calls.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any
from uuid import uuid4

import structlog
from strands import Agent
from strands.models import BedrockModel

from src.domain.models.entities import (
    Citation,
    ConfidenceScore,
    FallbackInfo,
    GenerationResult,
    ScoredChunk,
)

logger = structlog.get_logger(__name__)

DEFAULT_MODEL_ID = "apac.amazon.nova-pro-v1:0"
DEFAULT_REGION = "ap-southeast-4"
CONFIDENCE_THRESHOLD = 0.3


class GenerationService:
    """Generates grounded answers with citations from retrieved context.

    Uses a Strands Agent (Bedrock) to produce answers that:
    - Are grounded exclusively in retrieved chunks
    - Include bracketed citations [1], [2], etc.
    - State when context is insufficient
    - Provide confidence scoring
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region_name: str = DEFAULT_REGION,
    ) -> None:
        self._model_id = model_id
        self._region_name = region_name
        self._agent: Agent | None = None
        logger.info("generation_service.initialized", model_id=model_id, region=region_name)

    def _get_agent(self) -> Agent:
        """Lazy-load the generation agent."""
        if self._agent is None:
            model = BedrockModel(
                model_id=self._model_id,
                region_name=self._region_name,
                temperature=0.1,
                max_tokens=2048,
            )
            self._agent = Agent(
                model=model,
                system_prompt=(
                    "You are a precise RAG assistant. Answer questions using ONLY the "
                    "provided context. Cite sources with [1], [2], etc. matching the numbered "
                    "context blocks. If the context does not contain sufficient information, "
                    "explicitly state what is missing. Never make up information."
                ),
            )
        return self._agent

    async def generate(
        self,
        query: str,
        chunks: list[ScoredChunk],
        correlation_id: str = "",
    ) -> GenerationResult:
        """Generate a grounded answer with citations.

        Args:
            query: The user's question.
            chunks: Retrieved and reranked chunks.
            correlation_id: Request correlation ID.

        Returns:
            GenerationResult with answer, citations, confidence.
        """
        if not correlation_id:
            correlation_id = str(uuid4())

        start_time = time.perf_counter()

        if not chunks:
            return self._build_fallback(query, chunks, "No relevant chunks retrieved")

        context = self._format_context(chunks)
        retrieval_confidence = self._compute_retrieval_confidence(chunks)

        if retrieval_confidence < CONFIDENCE_THRESHOLD:
            return self._build_fallback(query, chunks, "Low retrieval confidence")

        # Generate with LLM
        prompt = (
            f"QUESTION: {query}\n\n"
            f"CONTEXT:\n{context}\n\n"
            "INSTRUCTIONS: Answer the question using ONLY the context above. "
            "Cite each claim with [N] references matching the context numbers. "
            "If the context is insufficient, say so explicitly."
        )

        try:
            agent = self._get_agent()
            response = agent(prompt)
            answer = str(response)
        except Exception as e:
            logger.error("generation_service.llm_failed", error=str(e), correlation_id=correlation_id)
            return self._build_fallback(query, chunks, f"Generation failed: {e}")

        # Extract and score
        citations = self._extract_citations(answer, chunks)
        citation_coverage = len(citations) / max(1, self._count_claims(answer))
        answer_completeness = min(1.0, 0.5 + len(citations) * 0.1)

        confidence = ConfidenceScore(
            retrieval_confidence=min(1.0, retrieval_confidence),
            citation_coverage=min(1.0, citation_coverage),
            answer_completeness=answer_completeness,
            composite=min(
                1.0,
                0.35 * retrieval_confidence + 0.40 * citation_coverage + 0.25 * answer_completeness,
            ),
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "generation_service.generate.success",
            answer_length=len(answer),
            citation_count=len(citations),
            composite=round(confidence.composite, 3),
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        return GenerationResult(
            answer=answer,
            citations=citations,
            context_chunks=chunks,
            confidence=confidence,
            is_fallback=False,
        )

    def _format_context(self, chunks: list[ScoredChunk]) -> str:
        """Format chunks into numbered context blocks."""
        blocks = []
        for i, sc in enumerate(chunks, 1):
            section = f" (Section: {sc.chunk.section_heading})" if sc.chunk.section_heading else ""
            blocks.append(f"[{i}]{section}\n{sc.chunk.text}")
        return "\n\n---\n\n".join(blocks)

    def _extract_citations(self, answer: str, chunks: list[ScoredChunk]) -> list[Citation]:
        """Extract citation references from the generated answer."""
        found_refs = re.findall(r"\[(\d+)\]", answer)
        unique_refs = sorted(set(int(r) for r in found_refs))

        citations = []
        for ref_num in unique_refs:
            if 1 <= ref_num <= len(chunks):
                chunk = chunks[ref_num - 1]
                cite_pattern = rf"[^.]*\[{ref_num}\][^.]*\."
                matches = re.findall(cite_pattern, answer)
                claim = matches[0].strip() if matches else f"Reference [{ref_num}]"

                citations.append(Citation(
                    index=ref_num,
                    chunk_id=chunk.chunk.id,
                    claim=claim[:200],
                    source_text=chunk.chunk.text[:300],
                    verified=True,
                ))
        return citations

    def _compute_retrieval_confidence(self, chunks: list[ScoredChunk]) -> float:
        """Compute retrieval confidence using sigmoid normalization of scores."""
        if not chunks:
            return 0.0
        avg_score = sum(sc.score for sc in chunks) / len(chunks)
        return min(1.0, max(0.0, 1.0 / (1.0 + math.exp(-avg_score * 0.3))))

    def _count_claims(self, answer: str) -> int:
        """Estimate factual claims by counting substantive sentences."""
        return max(1, len([s for s in answer.split(".") if len(s.strip()) > 20]))

    def _build_fallback(
        self, query: str, chunks: list[ScoredChunk], reason: str
    ) -> GenerationResult:
        """Build structured fallback response."""
        return GenerationResult(
            answer=(
                f"I could not generate a complete answer for: '{query}'. "
                f"Reason: {reason}. Found {len(chunks)} related chunks."
            ),
            citations=[],
            context_chunks=chunks,
            confidence=ConfidenceScore(
                retrieval_confidence=self._compute_retrieval_confidence(chunks),
                citation_coverage=0.0,
                answer_completeness=0.2,
                composite=0.1,
            ),
            is_fallback=True,
            fallback_info=FallbackInfo(
                found=[sc.chunk.section_heading for sc in chunks if sc.chunk.section_heading][:5],
                not_found=[query],
                suggested_documents=list({str(sc.chunk.document_id) for sc in chunks})[:5],
            ),
        )

"""Evaluation Agent — computes confidence scores and determines fallback responses.

Requirements: 4.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.agents.confidence_scorer import ConfidenceScorer
from src.agents.prompt_loader import load_prompt

if TYPE_CHECKING:
    from domain_models.api_models import CitationResponse, ConfidenceScoreResponse
    from domain_models.core import ScoredChunk

logger = structlog.get_logger(__name__)


class EvaluationAgent:
    """Computes confidence scores and determines fallback responses.

    Delegates to ConfidenceScorer for the actual computation.

    Loads its system prompt at initialization; raises ConfigurationError
    if the prompt is missing or empty (Requirement 4.5, 4.8).
    """

    def __init__(
        self,
        confidence_scorer: ConfidenceScorer | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the Evaluation Agent with its system prompt.

        Args:
            confidence_scorer: Optional scorer override.
            system_prompt: Optional system prompt override. If not provided,
                           loads from the prompts directory.

        Raises:
            ConfigurationError: If the prompt file is missing or empty.
        """
        self._scorer = confidence_scorer or ConfidenceScorer()
        self._system_prompt = system_prompt or load_prompt("evaluation_agent")

    @property
    def system_prompt(self) -> str:
        """Return the loaded system prompt for this agent."""
        return self._system_prompt

    async def evaluate(
        self,
        query: str,
        answer: str,
        chunks: list[ScoredChunk],
        citations: list[CitationResponse],
        correlation_id: str,
    ) -> ConfidenceScoreResponse:
        """Evaluate the answer quality and compute confidence scores.

        Args:
            query: The original user query.
            answer: The generated answer.
            chunks: Retrieved source chunks (post-reranking).
            citations: Verified citations.
            correlation_id: Request correlation ID.

        Returns:
            Confidence score breakdown.
        """
        logger.info("evaluation_agent.evaluate", correlation_id=correlation_id)

        confidence = self._scorer.compute(
            query=query,
            answer=answer,
            chunks=chunks,
            citations=citations,
        )

        logger.info(
            "evaluation_agent.complete",
            composite=confidence.composite,
            correlation_id=correlation_id,
        )
        return confidence

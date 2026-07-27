"""Generation Agent — produces cited answers from retrieved context.

Builds a deterministic answer from the top retrieved chunks by concatenating
section headings and text excerpts. In production this would call Bedrock via
Strands, but for now returns deterministic output suitable for testing.

Requirements: 4.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.agents.prompt_loader import load_prompt

if TYPE_CHECKING:
    from domain_models.core import ScoredChunk

logger = structlog.get_logger(__name__)


class GenerationAgent:
    """Generates cited answers from retrieved context.

    Accepts query + chunks and returns a generated answer string.
    For now, builds a simple answer from the top chunks (concatenate
    section headings + first 200 chars). In production this would call
    Bedrock via Strands.

    Loads its system prompt at initialization; raises ConfigurationError
    if the prompt is missing or empty (Requirement 4.2, 4.8).
    """

    def __init__(self, system_prompt: str | None = None) -> None:
        """Initialize the Generation Agent with its system prompt.

        Args:
            system_prompt: Optional system prompt override. If not provided,
                           loads from the prompts directory.

        Raises:
            ConfigurationError: If the prompt file is missing or empty.
        """
        self._system_prompt = system_prompt or load_prompt("generation_agent")

    @property
    def system_prompt(self) -> str:
        """Return the loaded system prompt for this agent."""
        return self._system_prompt

    async def generate(
        self, query: str, chunks: list[ScoredChunk], correlation_id: str
    ) -> str:
        """Generate an answer from retrieved chunks.

        Args:
            query: The user's natural language query.
            chunks: Retrieved and reranked source chunks.
            correlation_id: Request correlation ID.

        Returns:
            Generated answer text with inline citation markers [N].
        """
        logger.info("generation_agent.generate", query=query[:100], correlation_id=correlation_id)

        if not chunks:
            return "No relevant information was found for your query. Please try rephrasing or consult the legislation directly."

        # Build answer from top chunks with citation markers
        parts: list[str] = []
        for i, chunk in enumerate(chunks):
            heading = chunk.section_heading or "Unknown Section"
            text_excerpt = chunk.text[:200].strip()
            parts.append(f"According to {heading}, {text_excerpt} [{i + 1}].")

        answer = " ".join(parts)
        logger.info(
            "generation_agent.complete",
            chunk_count=len(chunks),
            answer_length=len(answer),
            correlation_id=correlation_id,
        )
        return answer

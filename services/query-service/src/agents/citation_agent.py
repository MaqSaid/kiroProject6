"""Citation Verification Agent — verifies citations against source chunks.

Extracts [N] references from the answer text and marks them as "verified"
if N <= len(chunks), otherwise marks them as "unsupported".

Requirements: 4.3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from domain_models.api_models import CitationResponse
from src.agents.prompt_loader import load_prompt

if TYPE_CHECKING:
    from domain_models.core import ScoredChunk

logger = structlog.get_logger(__name__)


class CitationVerificationAgent:
    """Verifies citations against source chunks.

    Extracts [N] references from the answer text and marks them as "verified"
    if the index N is within the bounds of the provided chunks list.

    Loads its system prompt at initialization; raises ConfigurationError
    if the prompt is missing or empty (Requirement 4.3, 4.8).
    """

    def __init__(self, system_prompt: str | None = None) -> None:
        """Initialize the Citation Verification Agent with its system prompt.

        Args:
            system_prompt: Optional system prompt override. If not provided,
                           loads from the prompts directory.

        Raises:
            ConfigurationError: If the prompt file is missing or empty.
        """
        self._system_prompt = system_prompt or load_prompt("citation_verification_agent")

    @property
    def system_prompt(self) -> str:
        """Return the loaded system prompt for this agent."""
        return self._system_prompt

    async def verify(
        self, answer: str, chunks: list[ScoredChunk], correlation_id: str
    ) -> list[CitationResponse]:
        """Verify citations in the generated answer.

        Args:
            answer: The generated answer text.
            chunks: Source chunks used for generation.
            correlation_id: Request correlation ID.

        Returns:
            List of CitationResponse with index, source_reference, claim,
            and verification_status.
        """
        logger.info("citation_agent.verify", correlation_id=correlation_id)

        if not answer or not chunks:
            return []

        # Extract [N] citation markers from the answer
        citation_pattern = re.compile(r"\[(\d+)\]")
        matches = citation_pattern.finditer(answer)

        citations: list[CitationResponse] = []
        seen_indices: set[int] = set()

        for match in matches:
            index = int(match.group(1))
            if index in seen_indices:
                continue
            seen_indices.add(index)

            # Extract surrounding context as the claim (up to 100 chars before marker)
            start_pos = max(0, match.start() - 100)
            claim_text = answer[start_pos : match.start()].strip()
            # Clean up to last sentence boundary if possible
            last_period = claim_text.rfind(".")
            if last_period > 0:
                claim_text = claim_text[last_period + 1 :].strip()
            if not claim_text:
                claim_text = f"Citation [{index}]"

            # Verify: index is valid if 1-based index <= len(chunks)
            if 1 <= index <= len(chunks):
                chunk = chunks[index - 1]
                source_ref = f"{chunk.document_id}, {chunk.section_heading}"
                verification_status = "verified"
            else:
                source_ref = f"Unknown source [{index}]"
                verification_status = "unsupported"

            citations.append(
                CitationResponse(
                    index=index,
                    source_reference=source_ref,
                    claim=claim_text,
                    verification_status=verification_status,
                )
            )

        logger.info(
            "citation_agent.complete",
            citation_count=len(citations),
            verified_count=sum(1 for c in citations if c.verification_status == "verified"),
            correlation_id=correlation_id,
        )
        return citations

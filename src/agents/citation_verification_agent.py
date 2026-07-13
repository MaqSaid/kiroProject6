"""Citation Verification Agent — validates citations using LLM-as-judge.

This agent takes generated answers with citations and verifies each
citation-claim pair against the source context. It acts as a quality
gate ensuring answer faithfulness.
"""

from __future__ import annotations

from typing import Any

import structlog
from strands import Agent, tool

from src.agents.base import AgentConfig, create_agent

logger = structlog.get_logger(__name__)


def _build_verification_tools() -> list[Any]:
    """Build Strands tool functions for citation verification."""

    @tool
    def parse_citation_pairs(answer: str, context: str) -> str:
        """Parse an answer into individual citation-claim pairs for verification.

        Extracts each sentence with a citation and pairs it with the
        referenced source text from the context.

        Args:
            answer: The generated answer containing [N] citation references.
            context: The formatted context used during generation.
        """
        import re

        # Split context into numbered blocks
        context_blocks = {}
        blocks = context.split("---")
        for i, block in enumerate(blocks, 1):
            context_blocks[i] = block.strip()

        # Find all sentences with citations
        citation_pattern = re.compile(r"([^.]*?\[(\d+)\][^.]*\.)")
        matches = citation_pattern.findall(answer)

        pairs = []
        for full_match, ref_num in matches:
            ref_int = int(ref_num)
            source_text = context_blocks.get(ref_int, "SOURCE NOT FOUND")

            pairs.append({
                "claim": full_match.strip(),
                "citation_index": ref_int,
                "source_text": source_text[:500],
                "source_available": ref_int in context_blocks,
            })

        result = {
            "pairs": pairs,
            "total_citations": len(pairs),
            "unique_sources_referenced": len(set(int(m[1]) for m in matches)),
            "available_sources": len(context_blocks),
        }

        return str(result)

    @tool
    def verify_single_citation(claim: str, source_text: str) -> str:
        """Verify whether a single claim is supported by its cited source text.

        Uses semantic analysis to determine if the claim can be reasonably
        inferred from the source. Returns a verification verdict.

        Args:
            claim: The specific claim made in the answer.
            source_text: The source text that the claim cites.
        """
        # The LLM agent will reason about this naturally
        # This tool structures the verification request
        verification_prompt = (
            f"CLAIM: {claim}\n\n"
            f"SOURCE: {source_text}\n\n"
            "VERDICT: Determine if the claim is SUPPORTED, PARTIALLY_SUPPORTED, "
            "or NOT_SUPPORTED by the source text. "
            "A claim is SUPPORTED if all factual assertions in it can be directly "
            "found or logically inferred from the source. "
            "It is PARTIALLY_SUPPORTED if some but not all assertions are backed. "
            "It is NOT_SUPPORTED if the source does not contain the claimed information."
        )
        return verification_prompt

    @tool
    def compute_verification_score(verification_results: str) -> str:
        """Compute an overall citation verification score from individual verdicts.

        Aggregates individual citation verdicts into a summary score:
        - SUPPORTED = 1.0
        - PARTIALLY_SUPPORTED = 0.5
        - NOT_SUPPORTED = 0.0

        Overall score = average of all citation scores.

        Args:
            verification_results: JSON string containing list of verification verdicts.
        """
        import ast

        try:
            results = ast.literal_eval(verification_results) if verification_results else []
        except (ValueError, SyntaxError):
            return str({
                "overall_score": 0.0,
                "error": "Could not parse verification results",
            })

        if not results:
            return str({
                "overall_score": 0.0,
                "total_verified": 0,
                "breakdown": {},
            })

        score_map = {
            "SUPPORTED": 1.0,
            "PARTIALLY_SUPPORTED": 0.5,
            "NOT_SUPPORTED": 0.0,
        }

        scores = []
        breakdown = {"supported": 0, "partially_supported": 0, "not_supported": 0}

        for result in results:
            verdict = "NOT_SUPPORTED"
            if isinstance(result, dict):
                verdict = result.get("verdict", "NOT_SUPPORTED").upper()
            elif isinstance(result, str):
                verdict = result.upper()

            score = score_map.get(verdict, 0.0)
            scores.append(score)

            if verdict == "SUPPORTED":
                breakdown["supported"] += 1
            elif verdict == "PARTIALLY_SUPPORTED":
                breakdown["partially_supported"] += 1
            else:
                breakdown["not_supported"] += 1

        overall_score = sum(scores) / len(scores) if scores else 0.0

        summary = {
            "overall_score": round(overall_score, 3),
            "total_verified": len(scores),
            "breakdown": breakdown,
            "flagged_citations": [
                i + 1
                for i, s in enumerate(scores)
                if s < 1.0
            ],
        }

        return str(summary)

    @tool
    def generate_verification_report(
        answer: str,
        verification_summary: str,
        citation_pairs: str,
    ) -> str:
        """Generate a complete verification report for the answer.

        Combines citation pair analysis, individual verdicts, and overall
        scoring into a final report that can be returned to the user.

        Args:
            answer: The original generated answer.
            verification_summary: JSON string of the verification score summary.
            citation_pairs: JSON string of the citation-claim pairs analyzed.
        """
        import ast

        try:
            summary = ast.literal_eval(verification_summary) if verification_summary else {}
            ast.literal_eval(citation_pairs) if citation_pairs else {}
        except (ValueError, SyntaxError):
            summary = {}

        overall_score = summary.get("overall_score", 0.0)
        total_verified = summary.get("total_verified", 0)
        breakdown = summary.get("breakdown", {})
        flagged = summary.get("flagged_citations", [])

        report = {
            "verification_passed": overall_score >= 0.7,
            "overall_score": overall_score,
            "total_citations_verified": total_verified,
            "breakdown": breakdown,
            "flagged_citation_indices": flagged,
            "recommendation": (
                "Answer is well-supported by sources."
                if overall_score >= 0.7
                else "Answer has unsupported citations. Review flagged references."
            ),
            "answer_length": len(answer),
        }

        return str(report)

    return [
        parse_citation_pairs,
        verify_single_citation,
        compute_verification_score,
        generate_verification_report,
    ]


VERIFICATION_SYSTEM_PROMPT = """You are a Citation Verification Agent for a RAG pipeline.

Your job is to verify that every citation in a generated answer is actually supported
by its referenced source material. You act as an LLM-as-judge.

## Verification Workflow

1. **Parse citation pairs** — Use parse_citation_pairs to extract each claim and its source.

2. **Verify each citation** — For each pair, use verify_single_citation to check support.
   Judge each claim as:
   - SUPPORTED: The claim is directly stated or clearly implied by the source
   - PARTIALLY_SUPPORTED: Some aspects of the claim are in the source, but not all
   - NOT_SUPPORTED: The source does not contain the information claimed

3. **Compute score** — Use compute_verification_score to calculate the overall score.

4. **Generate report** — Use generate_verification_report for the final summary.

## Judgment Criteria

Be strict but fair:
- Paraphrasing is acceptable — the exact words don't need to match
- Logical inferences from stated facts are SUPPORTED
- Combining information from the same source is SUPPORTED
- Claims that add information not in the source are NOT_SUPPORTED
- Claims that contradict the source are NOT_SUPPORTED
- Overgeneralizations beyond what the source states are PARTIALLY_SUPPORTED

## Important Rules

- Verify EVERY citation, not just a sample
- Base verdicts only on the provided source text, not your own knowledge
- Be consistent in your judgment standards across all citations
- If a claim has multiple citations, verify each reference independently
"""


def create_citation_verification_agent(
    config: AgentConfig | None = None,
) -> Agent:
    """Create a Citation Verification Agent for validating answer faithfulness.

    Args:
        config: Optional agent configuration.

    Returns:
        A Strands Agent configured for citation verification.
    """
    tools = _build_verification_tools()

    agent = create_agent(
        tools=tools,
        system_prompt=VERIFICATION_SYSTEM_PROMPT,
        config=config,
    )

    logger.info("citation_verification_agent.created", tool_count=len(tools))
    return agent

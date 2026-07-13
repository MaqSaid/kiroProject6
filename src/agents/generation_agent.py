"""Generation Agent — produces grounded answers with citations from retrieved context.

This agent takes retrieved chunks and a user query, generates an answer that is
strictly grounded in the provided context, includes bracketed citation references,
and explicitly states when context is insufficient.

It coordinates with the Citation Verification Agent for post-generation validation.
"""

from __future__ import annotations

from typing import Any

import structlog
from strands import Agent, tool

from src.agents.base import AgentConfig, create_agent

logger = structlog.get_logger(__name__)


def _build_generation_tools() -> list[Any]:
    """Build Strands tool functions for the generation agent."""

    @tool
    def format_context(retrieved_chunks: str) -> str:
        """Format retrieved chunks into a numbered context block for answer generation.

        Takes the retrieval results and formats them into a clear, numbered
        reference format that the generation step can cite with [1], [2], etc.

        Args:
            retrieved_chunks: JSON string of retrieved chunk results from the retrieval agent.
        """
        import ast

        try:
            chunks = ast.literal_eval(retrieved_chunks) if retrieved_chunks else []
        except (ValueError, SyntaxError):
            return "Error: Could not parse retrieved chunks."

        if not chunks:
            return "NO_CONTEXT_AVAILABLE: No relevant chunks were retrieved for this query."

        formatted_parts = []
        for i, chunk in enumerate(chunks, 1):
            section = chunk.get("section", "Unknown Section")
            doc_id = chunk.get("document_id", "unknown")
            text = chunk.get("text", "")
            score = chunk.get("score", 0.0)

            formatted_parts.append(
                f"[{i}] (Document: {doc_id}, Section: {section}, Relevance: {score:.3f})\n"
                f"{text}\n"
            )

        return "\n---\n".join(formatted_parts)

    @tool
    def generate_grounded_answer(query: str, formatted_context: str) -> str:
        """Generate a grounded answer using ONLY the provided context.

        Produces an answer that:
        - Cites sources using bracketed references [1], [2], etc.
        - Only uses information present in the context
        - Explicitly states when context is insufficient
        - Never hallucates or invents information

        Args:
            query: The user's original question.
            formatted_context: The numbered context block from format_context.
        """
        if "NO_CONTEXT_AVAILABLE" in formatted_context:
            return (
                "I don't have sufficient context to answer this question. "
                "No relevant document chunks were found in the knowledge base. "
                "Consider uploading relevant documentation or rephrasing your query."
            )

        # The agent itself will generate the answer using its LLM capabilities
        # This tool structures the prompt for the generation
        return (
            f"QUERY: {query}\n\n"
            f"CONTEXT:\n{formatted_context}\n\n"
            "INSTRUCTIONS: Generate a comprehensive answer to the query using ONLY "
            "the information in the context above. Cite each claim using bracketed "
            "references [1], [2], etc. corresponding to the context numbers. "
            "If the context does not contain enough information to fully answer, "
            "state what is known and what gaps exist."
        )

    @tool
    def extract_citations(answer: str, context: str) -> str:
        """Extract citation references from a generated answer and map them to source chunks.

        Parses [1], [2], etc. references from the answer and identifies
        which claims they support, which source text they reference,
        and whether the citation appears valid based on context.

        Args:
            answer: The generated answer containing bracketed citations.
            context: The formatted context that was used for generation.
        """
        import re

        # Find all citation references in the answer
        citation_pattern = re.compile(r"\[(\d+)\]")
        citations_found = citation_pattern.findall(answer)

        if not citations_found:
            return str({
                "citations": [],
                "uncited_claims": "Answer contains no citations. Manual review recommended.",
                "citation_count": 0,
            })

        unique_citations = sorted(set(int(c) for c in citations_found))

        # Parse context to get source mappings
        context_blocks = context.split("---")
        source_map: dict[int, str] = {}
        for i, block in enumerate(context_blocks, 1):
            source_map[i] = block.strip()[:200]

        citations = []
        for ref_num in unique_citations:
            # Find the sentence containing this citation
            pattern = rf"[^.]*\[{ref_num}\][^.]*\."
            matches = re.findall(pattern, answer)
            claim = matches[0].strip() if matches else f"Citation [{ref_num}] found"

            citations.append({
                "index": ref_num,
                "claim": claim,
                "source_text": source_map.get(ref_num, "Source not found"),
                "verified": ref_num in source_map,
            })

        result = {
            "citations": citations,
            "citation_count": len(citations),
            "total_references": len(citations_found),
            "unique_sources_cited": len(unique_citations),
        }

        return str(result)

    @tool
    def compute_confidence(
        answer: str,
        citations_info: str,
        retrieval_scores: str,
    ) -> str:
        """Compute confidence scores for the generated answer.

        Calculates three dimensions:
        - retrieval_confidence: Based on relevance scores of retrieved chunks
        - citation_coverage: Percentage of claims backed by verified citations
        - answer_completeness: Estimated coverage of the query's information needs

        Composite = 0.35 * retrieval + 0.40 * citation + 0.25 * completeness

        Args:
            answer: The generated answer text.
            citations_info: JSON string of citation extraction results.
            retrieval_scores: JSON string with retrieval score information.
        """
        import ast

        try:
            citations = ast.literal_eval(citations_info) if citations_info else {}
            scores = ast.literal_eval(retrieval_scores) if retrieval_scores else {}
        except (ValueError, SyntaxError):
            citations = {}
            scores = {}

        # Retrieval confidence: average of top-5 retrieval scores
        chunk_scores = []
        if isinstance(scores, list):
            chunk_scores = [s.get("score", 0.0) for s in scores[:5]]
        elif isinstance(scores, dict) and "chunks" in scores:
            chunk_scores = [s.get("score", 0.0) for s in scores["chunks"][:5]]

        retrieval_confidence = (
            sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.3
        )
        retrieval_confidence = min(1.0, max(0.0, retrieval_confidence))

        # Citation coverage: verified citations / total claims
        citation_list = citations.get("citations", [])
        if citation_list:
            verified_count = sum(1 for c in citation_list if c.get("verified", False))
            citation_coverage = verified_count / len(citation_list)
        else:
            citation_coverage = 0.0

        # Answer completeness: heuristic based on answer length and citation count
        answer_length = len(answer)
        has_citations = citations.get("citation_count", 0) > 0
        is_fallback = "don't have sufficient context" in answer.lower()

        if is_fallback:
            answer_completeness = 0.2
        elif answer_length > 200 and has_citations:
            answer_completeness = min(1.0, 0.5 + (citations.get("citation_count", 0) * 0.1))
        elif answer_length > 100:
            answer_completeness = 0.5
        else:
            answer_completeness = 0.3

        # Composite score
        composite = (
            0.35 * retrieval_confidence
            + 0.40 * citation_coverage
            + 0.25 * answer_completeness
        )

        confidence = {
            "retrieval_confidence": round(retrieval_confidence, 3),
            "citation_coverage": round(citation_coverage, 3),
            "answer_completeness": round(answer_completeness, 3),
            "composite": round(composite, 3),
            "is_fallback": is_fallback,
        }

        return str(confidence)

    @tool
    def build_fallback_response(query: str, partial_context: str) -> str:
        """Build a structured fallback response when confidence is below threshold.

        Creates a response that honestly states what was found, what wasn't,
        and suggests documents that may be worth manual review.

        Args:
            query: The original user query.
            partial_context: Any partial context that was retrieved.
        """
        import ast

        try:
            chunks = ast.literal_eval(partial_context) if partial_context else []
        except (ValueError, SyntaxError):
            chunks = []

        found_topics = []
        not_found = [query]
        suggested_docs = set()

        for chunk in chunks[:5] if isinstance(chunks, list) else []:
            if isinstance(chunk, dict):
                section = chunk.get("section", "")
                if section:
                    found_topics.append(section)
                doc_id = chunk.get("document_id", "")
                if doc_id:
                    suggested_docs.add(doc_id)

        fallback = {
            "is_fallback": True,
            "answer": (
                f"I could not find a complete answer to: '{query}'. "
                f"Here's what I found and what's missing."
            ),
            "found": found_topics[:5],
            "not_found": not_found,
            "suggested_documents": list(suggested_docs)[:5],
            "recommendation": "Consider uploading more relevant documentation or refining the query.",
        }

        return str(fallback)

    return [
        format_context,
        generate_grounded_answer,
        extract_citations,
        compute_confidence,
        build_fallback_response,
    ]


GENERATION_SYSTEM_PROMPT = """You are a Generation Agent for a RAG (Retrieval-Augmented Generation) pipeline.

Your job is to produce grounded, well-cited answers based on retrieved document context.

## Generation Workflow

1. **Format context** — Use format_context to organize retrieved chunks into numbered references.

2. **Generate answer** — Use generate_grounded_answer to produce an answer that:
   - Uses ONLY information from the provided context
   - Includes bracketed citations [1], [2], [3] for every factual claim
   - Clearly states when information is insufficient
   - Never hallucates or makes up information

3. **Extract citations** — Use extract_citations to parse and validate citation references.

4. **Compute confidence** — Use compute_confidence to assess answer quality across three dimensions.

5. **Handle fallbacks** — If confidence is below 0.4, use build_fallback_response to create a structured "I don't know" response.

## Citation Rules

- Every factual claim MUST have a bracketed citation [N]
- Citations must reference actual chunks from the context
- Multiple claims from the same chunk can share a citation
- If you cannot support a claim with context, state it explicitly

## Quality Standards

- Be concise but comprehensive
- Prefer direct quotes from source material over paraphrasing
- Group related information logically
- Start with the most relevant information first

## Confidence Threshold

- Composite score >= 0.6: Return the generated answer with citations
- Composite score >= 0.4: Return the answer but flag as low confidence
- Composite score < 0.4: Use build_fallback_response instead
"""


def create_generation_agent(
    config: AgentConfig | None = None,
) -> Agent:
    """Create a Generation Agent for producing grounded, cited answers.

    Args:
        config: Optional agent configuration.

    Returns:
        A Strands Agent configured for answer generation.
    """
    tools = _build_generation_tools()

    agent = create_agent(
        tools=tools,
        system_prompt=GENERATION_SYSTEM_PROMPT,
        config=config,
    )

    logger.info("generation_agent.created", tool_count=len(tools))
    return agent

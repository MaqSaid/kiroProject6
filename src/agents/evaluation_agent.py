"""Evaluation Agent — runs quality assessments against golden dataset.

This agent evaluates the RAG pipeline's quality by running test queries
from a golden dataset and computing metrics for answer correctness,
faithfulness, retrieval relevance, and citation accuracy.
"""

from __future__ import annotations

from typing import Any

import structlog
from strands import Agent, tool

from src.agents.base import AgentConfig, create_agent

logger = structlog.get_logger(__name__)


def _build_evaluation_tools() -> list[Any]:
    """Build Strands tool functions for evaluation."""

    @tool
    def load_golden_dataset(dataset_path: str) -> str:
        """Load the golden Q&A dataset for evaluation.

        Reads a JSON file containing hand-written question-answer pairs
        categorized by type (simple lookup, multi-hop, no-answer, ambiguous).

        Args:
            dataset_path: Path to the golden dataset JSON file.
        """
        import json
        from pathlib import Path

        path = Path(dataset_path)
        if not path.exists():
            return str({
                "error": f"Dataset not found: {dataset_path}",
                "success": False,
            })

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return str({
                "error": f"Invalid JSON: {e}",
                "success": False,
            })

        # Expected format: {"questions": [{"query": ..., "expected_answer": ..., "type": ...}]}
        questions = data.get("questions", data if isinstance(data, list) else [])

        categories: dict[str, int] = {}
        for q in questions:
            q_type = q.get("type", "unknown")
            categories[q_type] = categories.get(q_type, 0) + 1

        return str({
            "success": True,
            "total_questions": len(questions),
            "categories": categories,
            "sample_questions": [
                {
                    "query": q.get("query", "")[:100],
                    "type": q.get("type", "unknown"),
                }
                for q in questions[:5]
            ],
        })

    @tool
    def evaluate_answer_correctness(
        generated_answer: str,
        expected_answer: str,
        query: str,
    ) -> str:
        """Evaluate answer correctness using LLM-as-judge comparison.

        Compares the generated answer against the expected golden answer
        and produces a correctness score.

        Scoring:
        - 1.0: Fully correct, covers all key points
        - 0.75: Mostly correct, minor omissions
        - 0.5: Partially correct, significant gaps
        - 0.25: Mostly incorrect, few valid points
        - 0.0: Completely incorrect or irrelevant

        Args:
            generated_answer: The answer produced by the RAG pipeline.
            expected_answer: The hand-written golden answer.
            query: The original question.
        """
        # The LLM agent will reason about correctness using this structured prompt
        evaluation_prompt = (
            f"QUERY: {query}\n\n"
            f"EXPECTED ANSWER: {expected_answer}\n\n"
            f"GENERATED ANSWER: {generated_answer}\n\n"
            "EVALUATE: Compare the generated answer against the expected answer. "
            "Score the correctness on a scale of 0.0 to 1.0. Consider: "
            "Does it cover the same key facts? Are there factual errors? "
            "Are there significant omissions?"
        )
        return evaluation_prompt

    @tool
    def evaluate_faithfulness(
        generated_answer: str,
        context_chunks: str,
    ) -> str:
        """Evaluate answer faithfulness — does the answer stay grounded in context?

        Checks whether every claim in the generated answer can be traced
        back to the provided context chunks. Penalizes hallucinated content.

        Scoring:
        - 1.0: All claims grounded in context
        - 0.5: Some claims lack context support
        - 0.0: Mostly hallucinated

        Args:
            generated_answer: The answer to evaluate.
            context_chunks: JSON string of the context chunks used for generation.
        """
        evaluation_prompt = (
            f"ANSWER: {generated_answer}\n\n"
            f"CONTEXT: {context_chunks[:3000]}\n\n"
            "EVALUATE FAITHFULNESS: Check if every factual claim in the answer "
            "is supported by the provided context. Score 0.0-1.0. "
            "1.0 means fully grounded, 0.0 means mostly hallucinated. "
            "Identify any claims that go beyond what the context states."
        )
        return evaluation_prompt

    @tool
    def evaluate_retrieval_relevance(
        query: str,
        retrieved_chunks: str,
        expected_answer: str,
    ) -> str:
        """Evaluate retrieval relevance — did we fetch the right chunks?

        Assesses whether the retrieved chunks contain the information
        needed to answer the query correctly.

        Scoring:
        - 1.0: All needed information is in the retrieved chunks
        - 0.5: Some needed information is present
        - 0.0: Retrieved chunks are irrelevant

        Args:
            query: The original question.
            retrieved_chunks: JSON string of retrieved chunk texts.
            expected_answer: The expected golden answer (for reference).
        """
        evaluation_prompt = (
            f"QUERY: {query}\n\n"
            f"RETRIEVED CHUNKS: {retrieved_chunks[:3000]}\n\n"
            f"EXPECTED ANSWER (for reference): {expected_answer}\n\n"
            "EVALUATE RETRIEVAL: Do the retrieved chunks contain the information "
            "needed to produce the expected answer? Score 0.0-1.0. "
            "1.0 means all needed info is present. 0.0 means chunks are irrelevant."
        )
        return evaluation_prompt

    @tool
    def evaluate_citation_accuracy(
        generated_answer: str,
        context_chunks: str,
    ) -> str:
        """Evaluate citation accuracy — are citations pointing to the right sources?

        Checks that bracketed references [1], [2] etc. actually correspond
        to the source material that supports the cited claim.

        Scoring:
        - 1.0: All citations accurately reference supporting material
        - 0.5: Some citations are mismatched
        - 0.0: Citations don't correspond to sources

        Args:
            generated_answer: The answer with citation references.
            context_chunks: JSON string of the numbered context chunks.
        """
        evaluation_prompt = (
            f"ANSWER WITH CITATIONS: {generated_answer}\n\n"
            f"NUMBERED CONTEXT: {context_chunks[:3000]}\n\n"
            "EVALUATE CITATIONS: For each [N] reference in the answer, check "
            "if the referenced context chunk [N] actually supports the claim. "
            "Score 0.0-1.0 based on citation accuracy. "
            "1.0 = all citations point to correct sources. "
            "0.0 = citations are random/incorrect."
        )
        return evaluation_prompt

    @tool
    def compute_evaluation_summary(results: str) -> str:
        """Compute aggregate evaluation metrics from individual question results.

        Produces a summary report with averages per metric, breakdowns by
        question category, and identification of worst-performing areas.

        Args:
            results: JSON string of individual evaluation results.
        """
        import ast

        try:
            result_list = ast.literal_eval(results) if results else []
        except (ValueError, SyntaxError):
            return str({"error": "Could not parse results", "success": False})

        if not result_list:
            return str({
                "total_evaluated": 0,
                "message": "No results to aggregate.",
            })

        # Aggregate metrics
        metrics = {
            "correctness": [],
            "faithfulness": [],
            "retrieval_relevance": [],
            "citation_accuracy": [],
        }

        category_scores: dict[str, list[float]] = {}

        for result in result_list:
            if not isinstance(result, dict):
                continue
            for metric in metrics:
                score = result.get(metric, None)
                if score is not None:
                    metrics[metric].append(float(score))

            cat = result.get("category", "unknown")
            composite = result.get("composite_score", 0.0)
            if cat not in category_scores:
                category_scores[cat] = []
            category_scores[cat].append(float(composite))

        averages = {}
        for metric, scores in metrics.items():
            averages[metric] = round(sum(scores) / len(scores), 3) if scores else 0.0

        # Overall composite
        all_scores = []
        for scores in metrics.values():
            all_scores.extend(scores)
        overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

        # Category breakdown
        category_averages = {
            cat: round(sum(scores) / len(scores), 3)
            for cat, scores in category_scores.items()
            if scores
        }

        summary = {
            "total_evaluated": len(result_list),
            "overall_score": overall,
            "metric_averages": averages,
            "category_breakdown": category_averages,
            "best_metric": max(averages, key=averages.get) if averages else None,
            "worst_metric": min(averages, key=averages.get) if averages else None,
            "pass_rate": (
                sum(1 for r in result_list if r.get("composite_score", 0) >= 0.7)
                / len(result_list)
                if result_list
                else 0.0
            ),
        }

        return str(summary)

    @tool
    def compare_chunking_strategies(evaluation_results_by_strategy: str) -> str:
        """Compare evaluation results across different chunking strategies.

        Takes evaluation results from multiple strategy runs and identifies
        which strategy performs best per metric.

        Args:
            evaluation_results_by_strategy: JSON string mapping strategy name to results list.
        """
        import ast

        try:
            by_strategy = ast.literal_eval(evaluation_results_by_strategy) if evaluation_results_by_strategy else {}
        except (ValueError, SyntaxError):
            return str({"error": "Could not parse strategy results"})

        comparison: dict[str, dict[str, float]] = {}

        for strategy, results in by_strategy.items():
            if not isinstance(results, list):
                continue

            metrics_sum: dict[str, float] = {}
            metrics_count: dict[str, int] = {}

            for result in results:
                if not isinstance(result, dict):
                    continue
                for key in ["correctness", "faithfulness", "retrieval_relevance", "citation_accuracy"]:
                    if key in result:
                        metrics_sum[key] = metrics_sum.get(key, 0.0) + float(result[key])
                        metrics_count[key] = metrics_count.get(key, 0) + 1

            comparison[strategy] = {
                metric: round(metrics_sum[metric] / metrics_count[metric], 3)
                for metric in metrics_sum
                if metrics_count.get(metric, 0) > 0
            }

        # Determine winners per metric
        winners: dict[str, str] = {}
        for metric in ["correctness", "faithfulness", "retrieval_relevance", "citation_accuracy"]:
            best_strategy = None
            best_score = -1.0
            for strategy, scores in comparison.items():
                if scores.get(metric, 0.0) > best_score:
                    best_score = scores[metric]
                    best_strategy = strategy
            if best_strategy:
                winners[metric] = best_strategy

        report = {
            "strategies_compared": list(comparison.keys()),
            "scores_by_strategy": comparison,
            "winner_per_metric": winners,
            "overall_recommendation": (
                max(
                    comparison.keys(),
                    key=lambda s: sum(comparison[s].values()) / max(len(comparison[s]), 1),
                )
                if comparison
                else "insufficient_data"
            ),
        }

        return str(report)

    return [
        load_golden_dataset,
        evaluate_answer_correctness,
        evaluate_faithfulness,
        evaluate_retrieval_relevance,
        evaluate_citation_accuracy,
        compute_evaluation_summary,
        compare_chunking_strategies,
    ]


EVALUATION_SYSTEM_PROMPT = """You are an Evaluation Agent for a RAG (Retrieval-Augmented Generation) pipeline.

Your job is to assess the quality of the RAG pipeline by evaluating generated answers
against a golden dataset of hand-written Q&A pairs.

## Evaluation Workflow

1. **Load dataset** — Use load_golden_dataset to read the evaluation questions.

2. **For each question**, evaluate these dimensions:
   - **Correctness** — Does the answer match the expected golden answer?
   - **Faithfulness** — Is the answer grounded in the retrieved context?
   - **Retrieval Relevance** — Did we fetch the right chunks?
   - **Citation Accuracy** — Do citations point to correct sources?

3. **Score each dimension** on a 0.0 to 1.0 scale using LLM-as-judge reasoning.

4. **Compute summary** — Use compute_evaluation_summary for aggregate metrics.

5. **Compare strategies** — If results from multiple chunking strategies are available,
   use compare_chunking_strategies to identify the best approach.

## Scoring Guidelines

Be consistent and calibrated:
- 1.0 = Perfect, no issues
- 0.75 = Minor issues that don't affect understanding
- 0.5 = Significant issues but partially useful
- 0.25 = Mostly problematic, limited value
- 0.0 = Completely wrong or useless

## Question Categories

- **simple_lookup**: Single-fact answers from one document section
- **multi_hop**: Answers requiring information from multiple documents/sections
- **no_answer**: Questions the knowledge base cannot answer (should gracefully refuse)
- **ambiguous**: Questions with multiple valid interpretations

## Special Handling

- For "no_answer" questions: Score correctness based on whether the system
  correctly identified it cannot answer (fallback response = high score)
- For "ambiguous" questions: Accept multiple valid interpretations
- For "multi_hop" questions: Retrieval relevance should assess if all needed sources were found

## Output

Provide structured evaluation results with per-question scores and an overall summary.
"""


def create_evaluation_agent(
    config: AgentConfig | None = None,
) -> Agent:
    """Create an Evaluation Agent for RAG pipeline quality assessment.

    Args:
        config: Optional agent configuration.

    Returns:
        A Strands Agent configured for evaluation and benchmarking.
    """
    tools = _build_evaluation_tools()

    agent = create_agent(
        tools=tools,
        system_prompt=EVALUATION_SYSTEM_PROMPT,
        config=config,
    )

    logger.info("evaluation_agent.created", tool_count=len(tools))
    return agent

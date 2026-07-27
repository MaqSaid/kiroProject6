"""Evaluation harness runner for the Legislation RAG Platform.

Loads a golden dataset, queries the /v1/ask endpoint, computes metrics,
and produces a structured evaluation report.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from pathlib import Path

import httpx
import structlog

from tests.evaluation.metrics import (
    compute_calibration,
    compute_entity_recall,
    compute_mrr,
    compute_precision_at_k,
    compute_recall_at_k,
    compute_rouge_l,
)
from tests.evaluation.models import (
    AggregateMetrics,
    AnswerMetrics,
    BreakdownMetrics,
    EvaluationReport,
    EvaluationResult,
    GoldenItem,
    RetrievalMetrics,
)

logger = structlog.get_logger(__name__)


class EvaluationRunner:
    """Runs evaluation against the /v1/ask endpoint using a golden dataset."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        dataset_path: str = "data/golden_dataset.json",
        output_path: str = "reports/eval-metrics.json",
        top_k: int = 5,
        concurrency: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset_path = dataset_path
        self.output_path = output_path
        self.top_k = top_k
        self.concurrency = concurrency
        self.timeout = timeout
        self._semaphore: asyncio.Semaphore | None = None

    def load_dataset(self) -> list[GoldenItem]:
        """Load golden dataset from JSON file.

        Returns:
            List of GoldenItem instances parsed from the dataset file.

        Raises:
            FileNotFoundError: If the dataset file doesn't exist.
            ValueError: If the dataset JSON is malformed.
        """
        path = Path(self.dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")

        logger.info(
            "evaluation_runner.load_dataset.start",
            path=self.dataset_path,
        )

        with open(path) as f:
            raw = json.load(f)

        if not isinstance(raw, list):
            raise ValueError("Dataset must be a JSON array of golden items")

        items = [GoldenItem.model_validate(entry) for entry in raw]
        logger.info(
            "evaluation_runner.load_dataset.success",
            item_count=len(items),
        )
        return items

    async def _query_endpoint(
        self,
        client: httpx.AsyncClient,
        item: GoldenItem,
    ) -> EvaluationResult:
        """Query the /v1/ask endpoint for a single golden item.

        Handles errors gracefully so one failure doesn't stop the run.
        """
        assert self._semaphore is not None
        async with self._semaphore:
            start_time = time.perf_counter()
            correlation_id = str(uuid.uuid4())

            try:
                response = await client.post(
                    f"{self.base_url}/v1/ask",
                    json={"query": item.question, "top_k": self.top_k},
                    headers={"X-Correlation-ID": correlation_id},
                    timeout=self.timeout,
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code != 200:
                    logger.warning(
                        "evaluation_runner.query.http_error",
                        item_id=item.id,
                        status_code=response.status_code,
                    )
                    return EvaluationResult(
                        item_id=item.id,
                        question=item.question,
                        difficulty=item.difficulty,
                        category=item.category,
                        latency_ms=elapsed_ms,
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        correlation_id=correlation_id,
                    )

                data = response.json()
                actual_answer = data.get("answer", "")
                actual_citations = data.get("citations", [])
                actual_confidence = data.get("confidence")

                # Compute per-item metrics
                rouge_l = compute_rouge_l(actual_answer, item.expected_answer)
                entity_recall = compute_entity_recall(
                    actual_answer, item.expected_entities
                )
                length_ratio = (
                    len(actual_answer) / len(item.expected_answer)
                    if item.expected_answer
                    else 0.0
                )

                mrr = compute_mrr(actual_citations, item.expected_citations)
                recall_at_k = compute_recall_at_k(
                    actual_citations, item.expected_citations, k=self.top_k
                )
                precision_at_k = compute_precision_at_k(
                    actual_citations, item.expected_citations, k=self.top_k
                )

                result = EvaluationResult(
                    item_id=item.id,
                    question=item.question,
                    difficulty=item.difficulty,
                    category=item.category,
                    actual_answer=actual_answer,
                    actual_citations=actual_citations,
                    actual_confidence=actual_confidence,
                    retrieval_metrics=RetrievalMetrics(
                        mrr=round(mrr, 4),
                        recall_at_k=round(recall_at_k, 4),
                        precision_at_k=round(precision_at_k, 4),
                        k=self.top_k,
                    ),
                    answer_metrics=AnswerMetrics(
                        rouge_l=round(rouge_l, 4),
                        entity_recall=round(entity_recall, 4),
                        length_ratio=round(length_ratio, 4),
                    ),
                    latency_ms=round(elapsed_ms, 2),
                    success=True,
                    correlation_id=correlation_id,
                )

                logger.debug(
                    "evaluation_runner.query.success",
                    item_id=item.id,
                    latency_ms=elapsed_ms,
                    rouge_l=rouge_l,
                )
                return result

            except httpx.TimeoutException:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "evaluation_runner.query.timeout",
                    item_id=item.id,
                    timeout=self.timeout,
                )
                return EvaluationResult(
                    item_id=item.id,
                    question=item.question,
                    difficulty=item.difficulty,
                    category=item.category,
                    latency_ms=elapsed_ms,
                    success=False,
                    error=f"Timeout after {self.timeout}s",
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "evaluation_runner.query.failed",
                    item_id=item.id,
                    error=str(exc),
                )
                return EvaluationResult(
                    item_id=item.id,
                    question=item.question,
                    difficulty=item.difficulty,
                    category=item.category,
                    latency_ms=elapsed_ms,
                    success=False,
                    error=str(exc),
                    correlation_id=correlation_id,
                )

    def _compute_aggregate(self, results: list[EvaluationResult]) -> AggregateMetrics:
        """Compute aggregate metrics across all results."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not successful:
            return AggregateMetrics(
                total_items=len(results),
                successful_items=0,
                failed_items=len(failed),
            )

        latencies = [r.latency_ms for r in successful]
        mrr_scores = [
            r.retrieval_metrics.mrr for r in successful if r.retrieval_metrics
        ]
        recall_scores = [
            r.retrieval_metrics.recall_at_k for r in successful if r.retrieval_metrics
        ]
        precision_scores = [
            r.retrieval_metrics.precision_at_k
            for r in successful
            if r.retrieval_metrics
        ]
        rouge_scores = [
            r.answer_metrics.rouge_l for r in successful if r.answer_metrics
        ]
        entity_scores = [
            r.answer_metrics.entity_recall for r in successful if r.answer_metrics
        ]
        length_ratios = [
            r.answer_metrics.length_ratio for r in successful if r.answer_metrics
        ]

        calibration = compute_calibration(results)

        return AggregateMetrics(
            total_items=len(results),
            successful_items=len(successful),
            failed_items=len(failed),
            mean_latency_ms=round(statistics.mean(latencies), 2),
            std_latency_ms=round(
                statistics.stdev(latencies) if len(latencies) > 1 else 0.0, 2
            ),
            mean_mrr=round(statistics.mean(mrr_scores), 4) if mrr_scores else 0.0,
            mean_recall_at_k=round(statistics.mean(recall_scores), 4)
            if recall_scores
            else 0.0,
            mean_precision_at_k=round(statistics.mean(precision_scores), 4)
            if precision_scores
            else 0.0,
            mean_rouge_l=round(statistics.mean(rouge_scores), 4)
            if rouge_scores
            else 0.0,
            mean_entity_recall=round(statistics.mean(entity_scores), 4)
            if entity_scores
            else 0.0,
            mean_length_ratio=round(statistics.mean(length_ratios), 4)
            if length_ratios
            else 0.0,
            calibration=calibration,
        )

    def _compute_breakdown(
        self, results: list[EvaluationResult], dimension: str
    ) -> BreakdownMetrics:
        """Compute metrics broken down by a dimension (difficulty or category)."""
        groups: dict[str, list[EvaluationResult]] = {}
        for r in results:
            key = getattr(r, dimension)
            groups.setdefault(key, []).append(r)

        breakdown = BreakdownMetrics(dimension=dimension)
        for group_name, group_results in groups.items():
            breakdown.groups[group_name] = self._compute_aggregate(group_results)

        return breakdown

    def _compute_latency_percentiles(
        self, results: list[EvaluationResult]
    ) -> dict[str, float]:
        """Compute latency percentiles (p50, p95, p99)."""
        latencies = sorted(r.latency_ms for r in results if r.success)
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        def percentile(data: list[float], p: float) -> float:
            idx = (len(data) - 1) * (p / 100.0)
            lower = int(idx)
            upper = lower + 1
            if upper >= len(data):
                return data[-1]
            weight = idx - lower
            return data[lower] * (1 - weight) + data[upper] * weight

        return {
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
        }

    async def run(self) -> EvaluationReport:
        """Execute the full evaluation pipeline.

        Returns:
            EvaluationReport with all metrics and per-item results.
        """
        run_id = str(uuid.uuid4())
        logger.info(
            "evaluation_runner.run.start",
            run_id=run_id,
            base_url=self.base_url,
            dataset_path=self.dataset_path,
            concurrency=self.concurrency,
            top_k=self.top_k,
        )

        # Load dataset
        items = self.load_dataset()

        # Set up concurrency limiter
        self._semaphore = asyncio.Semaphore(self.concurrency)

        # Query all items concurrently (bounded)
        start_time = time.perf_counter()
        async with httpx.AsyncClient() as client:
            tasks = [self._query_endpoint(client, item) for item in items]
            results = await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time

        # Compute metrics
        aggregate = self._compute_aggregate(results)
        by_difficulty = self._compute_breakdown(results, "difficulty")
        by_category = self._compute_breakdown(results, "category")
        latency_percentiles = self._compute_latency_percentiles(results)

        report = EvaluationReport(
            run_id=run_id,
            base_url=self.base_url,
            dataset_path=self.dataset_path,
            total_duration_seconds=round(total_duration, 2),
            aggregate=aggregate,
            by_difficulty=by_difficulty,
            by_category=by_category,
            results=list(results),
            metadata={
                "top_k": self.top_k,
                "concurrency": self.concurrency,
                "timeout_seconds": self.timeout,
                "latency_p50_ms": latency_percentiles["p50"],
                "latency_p95_ms": latency_percentiles["p95"],
                "latency_p99_ms": latency_percentiles["p99"],
            },
        )

        logger.info(
            "evaluation_runner.run.complete",
            run_id=run_id,
            total_items=aggregate.total_items,
            successful=aggregate.successful_items,
            failed=aggregate.failed_items,
            duration_seconds=round(total_duration, 2),
            mean_rouge_l=aggregate.mean_rouge_l,
            mean_mrr=aggregate.mean_mrr,
        )

        return report

    def save_report(self, report: EvaluationReport) -> Path:
        """Save the evaluation report to JSON.

        Args:
            report: The evaluation report to serialize.

        Returns:
            Path to the written report file.
        """
        output = Path(self.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w") as f:
            f.write(report.model_dump_json(indent=2))

        logger.info(
            "evaluation_runner.save_report.success",
            path=str(output),
        )
        return output

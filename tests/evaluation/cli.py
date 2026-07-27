"""CLI entry point for the evaluation harness.

Usage:
    python -m tests.evaluation.cli --base-url http://localhost:8080

Runs the evaluation pipeline and prints a summary table to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from tests.evaluation.runner import EvaluationRunner

logger = structlog.get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="evaluation-harness",
        description="Run evaluation harness against the Legislation RAG /v1/ask endpoint.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Base URL of the RAG API (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--dataset",
        default="data/golden_dataset.json",
        help="Path to golden dataset JSON file (default: data/golden_dataset.json)",
    )
    parser.add_argument(
        "--output",
        default="reports/eval-metrics.json",
        help="Path for evaluation report output (default: reports/eval-metrics.json)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent requests to the API (default: 5)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of citations to request (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )
    return parser.parse_args(argv)


def print_summary_table(report) -> None:  # noqa: ANN001
    """Print a formatted summary table to stdout."""
    agg = report.aggregate
    meta = report.metadata

    separator = "=" * 60
    print(f"\n{separator}")
    print("  EVALUATION REPORT SUMMARY")
    print(separator)

    print(f"\n  Run ID:     {report.run_id}")
    print(f"  Endpoint:   {report.base_url}")
    print(f"  Dataset:    {report.dataset_path}")
    print(f"  Duration:   {report.total_duration_seconds:.1f}s")

    print(f"\n{'─' * 60}")
    print("  COVERAGE")
    print(f"{'─' * 60}")
    print(f"  Total items:      {agg.total_items}")
    print(f"  Successful:       {agg.successful_items}")
    print(f"  Failed:           {agg.failed_items}")

    success_rate = (
        (agg.successful_items / agg.total_items * 100) if agg.total_items > 0 else 0
    )
    print(f"  Success rate:     {success_rate:.1f}%")

    print(f"\n{'─' * 60}")
    print("  ANSWER QUALITY")
    print(f"{'─' * 60}")
    print(f"  ROUGE-L (mean):       {agg.mean_rouge_l:.4f}")
    print(f"  Entity Recall (mean): {agg.mean_entity_recall:.4f}")
    print(f"  Length Ratio (mean):  {agg.mean_length_ratio:.4f}")

    print(f"\n{'─' * 60}")
    print("  RETRIEVAL QUALITY")
    print(f"{'─' * 60}")
    print(f"  MRR (mean):           {agg.mean_mrr:.4f}")
    print(f"  Recall@{meta.get('top_k', 5)} (mean):      {agg.mean_recall_at_k:.4f}")
    print(f"  Precision@{meta.get('top_k', 5)} (mean):   {agg.mean_precision_at_k:.4f}")

    print(f"\n{'─' * 60}")
    print("  LATENCY")
    print(f"{'─' * 60}")
    print(f"  Mean:   {agg.mean_latency_ms:.1f} ms")
    print(f"  Std:    {agg.std_latency_ms:.1f} ms")
    print(f"  p50:    {meta.get('latency_p50_ms', 0):.1f} ms")
    print(f"  p95:    {meta.get('latency_p95_ms', 0):.1f} ms")
    print(f"  p99:    {meta.get('latency_p99_ms', 0):.1f} ms")

    if agg.calibration:
        print(f"\n{'─' * 60}")
        print("  CALIBRATION")
        print(f"{'─' * 60}")
        print(f"  ECE:                  {agg.calibration.expected_calibration_error:.4f}")
        print(f"  Overconfidence rate:  {agg.calibration.overconfidence_rate:.4f}")

    # Breakdown by difficulty
    if report.by_difficulty.groups:
        print(f"\n{'─' * 60}")
        print("  BREAKDOWN BY DIFFICULTY")
        print(f"{'─' * 60}")
        print(f"  {'Difficulty':<12} {'ROUGE-L':>8} {'MRR':>8} {'Recall@K':>10} {'Count':>6}")
        print(f"  {'─' * 48}")
        for name, metrics in sorted(report.by_difficulty.groups.items()):
            print(
                f"  {name:<12} {metrics.mean_rouge_l:>8.4f} "
                f"{metrics.mean_mrr:>8.4f} {metrics.mean_recall_at_k:>10.4f} "
                f"{metrics.total_items:>6}"
            )

    # Breakdown by category
    if report.by_category.groups:
        print(f"\n{'─' * 60}")
        print("  BREAKDOWN BY CATEGORY")
        print(f"{'─' * 60}")
        print(f"  {'Category':<12} {'ROUGE-L':>8} {'MRR':>8} {'Recall@K':>10} {'Count':>6}")
        print(f"  {'─' * 48}")
        for name, metrics in sorted(report.by_category.groups.items()):
            print(
                f"  {name:<12} {metrics.mean_rouge_l:>8.4f} "
                f"{metrics.mean_mrr:>8.4f} {metrics.mean_recall_at_k:>10.4f} "
                f"{metrics.total_items:>6}"
            )

    print(f"\n{separator}")
    print(f"  Report saved to: {report.metadata.get('output_path', 'reports/eval-metrics.json')}")
    print(f"{separator}\n")


async def async_main(args: argparse.Namespace) -> int:
    """Async entry point for the evaluation harness."""
    runner = EvaluationRunner(
        base_url=args.base_url,
        dataset_path=args.dataset,
        output_path=args.output,
        top_k=args.top_k,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )

    try:
        report = await runner.run()
    except FileNotFoundError as exc:
        logger.error("evaluation_cli.dataset_not_found", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.error("evaluation_cli.run_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Save report
    report.metadata["output_path"] = args.output
    output_path = runner.save_report(report)
    logger.info("evaluation_cli.report_saved", path=str(output_path))

    # Print summary
    print_summary_table(report)

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())

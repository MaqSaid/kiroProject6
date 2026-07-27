"""Pydantic models for the evaluation harness.

Defines schemas for golden dataset entries, evaluation results, metrics,
and the full evaluation report.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GoldenItemMetadata(BaseModel):
    """Metadata for a golden dataset entry."""

    legislation: str
    topic: str
    requires_multi_hop: bool = False


class GoldenItem(BaseModel):
    """Schema for a single golden dataset entry."""

    id: str
    question: str
    expected_answer: str
    expected_entities: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    difficulty: str = "simple"
    category: str = "factual"
    metadata: GoldenItemMetadata


class RetrievalMetrics(BaseModel):
    """Metrics for retrieval quality."""

    mrr: float = Field(description="Mean Reciprocal Rank")
    recall_at_k: float = Field(description="Recall@K — fraction of expected citations found")
    precision_at_k: float = Field(
        description="Precision@K — fraction of retrieved that are relevant"
    )
    k: int = Field(default=5, description="K value used for Recall/Precision@K")


class AnswerMetrics(BaseModel):
    """Metrics for answer quality."""

    rouge_l: float = Field(description="ROUGE-L F1 score based on LCS")
    entity_recall: float = Field(description="Fraction of expected entities found in answer")
    length_ratio: float = Field(description="Ratio of actual answer length to expected")


class CalibrationMetrics(BaseModel):
    """Metrics for confidence calibration."""

    expected_calibration_error: float = Field(description="ECE with 10 bins")
    overconfidence_rate: float = Field(description="Fraction of predictions overconfident")


class EvaluationResult(BaseModel):
    """Result for a single evaluated query."""

    item_id: str
    question: str
    difficulty: str
    category: str
    actual_answer: str | None = None
    actual_citations: list[str] = Field(default_factory=list)
    actual_confidence: float | None = None
    retrieval_metrics: RetrievalMetrics | None = None
    answer_metrics: AnswerMetrics | None = None
    latency_ms: float = 0.0
    success: bool = False
    error: str | None = None
    correlation_id: str = ""


class AggregateMetrics(BaseModel):
    """Aggregate metrics across all evaluation items."""

    total_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    mean_latency_ms: float = 0.0
    std_latency_ms: float = 0.0
    mean_mrr: float = 0.0
    mean_recall_at_k: float = 0.0
    mean_precision_at_k: float = 0.0
    mean_rouge_l: float = 0.0
    mean_entity_recall: float = 0.0
    mean_length_ratio: float = 0.0
    calibration: CalibrationMetrics | None = None


class BreakdownMetrics(BaseModel):
    """Metrics broken down by a category dimension."""

    dimension: str
    groups: dict[str, AggregateMetrics] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """Full evaluation report with aggregate metrics and per-item results."""

    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    base_url: str
    dataset_path: str
    total_duration_seconds: float = 0.0
    aggregate: AggregateMetrics = Field(default_factory=AggregateMetrics)
    by_difficulty: BreakdownMetrics = Field(
        default_factory=lambda: BreakdownMetrics(dimension="difficulty")
    )
    by_category: BreakdownMetrics = Field(
        default_factory=lambda: BreakdownMetrics(dimension="category")
    )
    results: list[EvaluationResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

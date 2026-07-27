"""Evaluation harness for the Legislation RAG Platform.

Provides golden-dataset-based evaluation with ROUGE-L, entity recall,
retrieval MRR, recall@k, precision@k, and confidence calibration metrics.
"""

from tests.evaluation.metrics import (
    compute_calibration,
    compute_entity_recall,
    compute_mrr,
    compute_precision_at_k,
    compute_recall_at_k,
    compute_rouge_l,
)
from tests.evaluation.runner import EvaluationRunner

__all__ = [
    "EvaluationRunner",
    "compute_calibration",
    "compute_entity_recall",
    "compute_mrr",
    "compute_precision_at_k",
    "compute_recall_at_k",
    "compute_rouge_l",
]

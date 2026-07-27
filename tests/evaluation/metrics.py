"""Metric computation functions for the evaluation harness.

Provides ROUGE-L, entity recall, retrieval MRR, recall@k, precision@k,
and confidence calibration metrics.
"""

from __future__ import annotations

from tests.evaluation.models import CalibrationMetrics, EvaluationResult


def _lcs_length(seq_a: list[str], seq_b: list[str]) -> int:
    """Compute length of longest common subsequence between two token lists."""
    m, n = len(seq_a), len(seq_b)
    if m == 0 or n == 0:
        return 0
    # Use O(min(m,n)) space
    if m < n:
        seq_a, seq_b = seq_b, seq_a
        m, n = n, m
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def compute_rouge_l(actual: str, expected: str) -> float:
    """Compute ROUGE-L F1 score based on longest common subsequence.

    Args:
        actual: The generated answer text.
        expected: The reference/expected answer text.

    Returns:
        ROUGE-L F1 score in [0.0, 1.0].
    """
    if not actual or not expected:
        return 0.0

    actual_tokens = actual.lower().split()
    expected_tokens = expected.lower().split()

    if not actual_tokens or not expected_tokens:
        return 0.0

    lcs_len = _lcs_length(actual_tokens, expected_tokens)

    if lcs_len == 0:
        return 0.0

    precision = lcs_len / len(actual_tokens)
    recall = lcs_len / len(expected_tokens)

    f1 = (2 * precision * recall) / (precision + recall)
    return f1


def compute_entity_recall(actual_answer: str, expected_entities: list[str]) -> float:
    """Compute fraction of expected entities found in the actual answer.

    Args:
        actual_answer: The generated answer text.
        expected_entities: List of entity strings expected to appear.

    Returns:
        Fraction of entities found in [0.0, 1.0].
    """
    if not expected_entities:
        return 1.0

    if not actual_answer:
        return 0.0

    answer_lower = actual_answer.lower()
    found = sum(1 for entity in expected_entities if entity.lower() in answer_lower)
    return found / len(expected_entities)


def compute_mrr(actual_citations: list[str], expected_citations: list[str]) -> float:
    """Compute Mean Reciprocal Rank for retrieved citations.

    Finds the rank of the first relevant citation in the actual list
    and returns 1/rank. If no relevant citation is found, returns 0.

    Args:
        actual_citations: Ordered list of retrieved citation identifiers.
        expected_citations: Set of relevant citation identifiers.

    Returns:
        MRR score in [0.0, 1.0].
    """
    if not expected_citations or not actual_citations:
        return 0.0

    expected_set = set(c.lower() for c in expected_citations)

    for rank, citation in enumerate(actual_citations, start=1):
        if citation.lower() in expected_set:
            return 1.0 / rank

    return 0.0


def compute_recall_at_k(
    actual_citations: list[str],
    expected_citations: list[str],
    k: int = 5,
) -> float:
    """Compute Recall@K -- fraction of expected citations found in top-k results.

    Args:
        actual_citations: Ordered list of retrieved citation identifiers.
        expected_citations: Set of relevant citation identifiers.
        k: Number of top results to consider.

    Returns:
        Recall@K in [0.0, 1.0].
    """
    if not expected_citations:
        return 1.0

    if not actual_citations:
        return 0.0

    top_k = set(c.lower() for c in actual_citations[:k])
    expected_set = set(c.lower() for c in expected_citations)

    found = len(top_k & expected_set)
    return found / len(expected_set)


def compute_precision_at_k(
    actual_citations: list[str],
    expected_citations: list[str],
    k: int = 5,
) -> float:
    """Compute Precision@K -- fraction of top-k results that are relevant.

    Args:
        actual_citations: Ordered list of retrieved citation identifiers.
        expected_citations: Set of relevant citation identifiers.
        k: Number of top results to consider.

    Returns:
        Precision@K in [0.0, 1.0].
    """
    if not actual_citations:
        return 0.0

    top_k = [c.lower() for c in actual_citations[:k]]
    expected_set = set(c.lower() for c in expected_citations)

    relevant_in_top_k = sum(1 for c in top_k if c in expected_set)
    return relevant_in_top_k / len(top_k)


def compute_calibration(
    results: list[EvaluationResult],
    num_bins: int = 10,
) -> CalibrationMetrics:
    """Compute confidence calibration metrics (ECE and overconfidence rate).

    Groups predictions into bins by confidence score and compares average
    confidence with actual accuracy in each bin.

    Args:
        results: List of evaluation results with confidence scores.
        num_bins: Number of equal-width bins for calibration.

    Returns:
        CalibrationMetrics with ECE and overconfidence rate.
    """
    # Filter to results that have confidence scores and were successful
    scored = [
        r for r in results if r.actual_confidence is not None and r.success
    ]

    if not scored:
        return CalibrationMetrics(
            expected_calibration_error=0.0,
            overconfidence_rate=0.0,
        )

    bin_width = 1.0 / num_bins
    bin_confidences: list[list[float]] = [[] for _ in range(num_bins)]
    bin_accuracies: list[list[float]] = [[] for _ in range(num_bins)]

    for result in scored:
        confidence = result.actual_confidence or 0.0
        # Determine accuracy based on ROUGE-L threshold
        accuracy = 1.0 if (
            result.answer_metrics is not None and result.answer_metrics.rouge_l >= 0.5
        ) else 0.0

        bin_idx = min(int(confidence / bin_width), num_bins - 1)
        bin_confidences[bin_idx].append(confidence)
        bin_accuracies[bin_idx].append(accuracy)

    # Compute ECE
    total_samples = len(scored)
    ece = 0.0
    overconfident_count = 0

    for i in range(num_bins):
        if not bin_confidences[i]:
            continue
        n_bin = len(bin_confidences[i])
        avg_confidence = sum(bin_confidences[i]) / n_bin
        avg_accuracy = sum(bin_accuracies[i]) / n_bin

        ece += (n_bin / total_samples) * abs(avg_accuracy - avg_confidence)

        if avg_confidence > avg_accuracy:
            overconfident_count += n_bin

    overconfidence_rate = overconfident_count / total_samples if total_samples > 0 else 0.0

    return CalibrationMetrics(
        expected_calibration_error=round(ece, 4),
        overconfidence_rate=round(overconfidence_rate, 4),
    )

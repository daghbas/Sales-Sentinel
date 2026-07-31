from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_fscore_support


def regression_metrics(actual, predicted) -> dict[str, float]:  # type: ignore[no-untyped-def]
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    error = y - p
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(np.square(error))))
    denom = float(np.sum(np.abs(y)))
    wape = float(np.sum(np.abs(error)) / denom) if denom > 1e-12 else 0.0
    smape = float(np.mean(2.0 * np.abs(error) / np.maximum(np.abs(y) + np.abs(p), 1e-12)))
    return {"mae": mae, "rmse": rmse, "wape": wape, "smape": smape}


def decline_classification_metrics(actual, predicted_median, probabilities, threshold: float = 0.10) -> dict[str, float]:  # type: ignore[no-untyped-def]
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted_median, dtype=float)
    probs = np.asarray(probabilities, dtype=float)
    baseline = np.roll(y, 7)
    baseline[:7] = np.maximum(np.mean(y[:14]), 1e-9)
    actual_decline = (y < baseline * (1.0 - threshold)).astype(int)
    predicted_decline = (p < baseline * (1.0 - threshold)).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual_decline, predicted_decline, average="binary", zero_division=0
    )
    try:
        pr_auc = float(average_precision_score(actual_decline, probs))
    except ValueError:
        pr_auc = 0.0
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1), "pr_auc": pr_auc}


def decline_metrics(actual_labels, probabilities, threshold: float = 0.5) -> dict[str, float]:  # type: ignore[no-untyped-def]
    """Evaluate decline-event probabilities against binary labels."""
    labels = np.asarray(actual_labels, dtype=int)
    probs = np.asarray(probabilities, dtype=float)
    predicted = (probs >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predicted, average="binary", zero_division=0
    )
    try:
        pr_auc = float(average_precision_score(labels, probs))
    except ValueError:
        pr_auc = 0.0
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": pr_auc,
    }

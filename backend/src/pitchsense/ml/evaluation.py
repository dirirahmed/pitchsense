"""Evaluation metrics for the three-way match prediction task.

Two metrics are reported throughout the project:

- `accuracy` — the share of matches whose highest-probability class matches the result.
  Simple to interpret, but insensitive to *how confident* each prediction was.
- `log_loss` — the negative log-likelihood of the true class. Rewards calibrated
  probabilities and heavily punishes a confident wrong call. Lower is better.

Probabilities are clipped to a small epsilon before taking logs so a degenerate "0%"
prediction on a class that does happen doesn't blow up the loss.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import accuracy_score, log_loss

EPSILON = 1e-15


@dataclass(frozen=True, slots=True)
class Metrics:
    accuracy: float
    log_loss: float
    n_samples: int

    def as_dict(self) -> dict[str, float | int]:
        return {"accuracy": self.accuracy, "log_loss": self.log_loss, "n_samples": self.n_samples}


def evaluate(y_true: np.ndarray, y_proba: np.ndarray) -> Metrics:
    """Return accuracy and log loss for one set of predicted probabilities."""
    if y_proba.ndim != 2 or y_proba.shape[1] != 3:
        raise ValueError(f"Expected (n, 3) probability matrix, got shape {y_proba.shape}")
    if y_true.shape[0] != y_proba.shape[0]:
        raise ValueError(
            f"Labels and probabilities length mismatch: {y_true.shape[0]} vs {y_proba.shape[0]}"
        )

    y_pred = np.argmax(y_proba, axis=1)
    acc = float(accuracy_score(y_true, y_pred))
    loss = float(log_loss(y_true, np.clip(y_proba, EPSILON, 1 - EPSILON), labels=[0, 1, 2]))
    return Metrics(accuracy=acc, log_loss=loss, n_samples=int(y_true.shape[0]))

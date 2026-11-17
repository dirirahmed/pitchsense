"""Benchmark predictors that the trained models have to beat.

- `always_home_probabilities` — the trivial "home team always wins" rule.
- `bet365_implied_probabilities` — the bookmaker's view, with the overround removed
  so the three outcomes sum to one. This is a much stronger baseline than it looks:
  a published odds price already folds in form, injuries and market sentiment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pitchsense.ml.features import Outcome


def always_home_probabilities(n: int) -> np.ndarray:
    """Return an (n, 3) matrix that places all mass on the home-win class."""
    probs = np.zeros((n, 3))
    probs[:, int(Outcome.HOME_WIN)] = 1.0
    return probs


def bet365_implied_probabilities(odds: pd.DataFrame) -> np.ndarray:
    """Convert Bet365 decimal odds into normalised H/D/A probabilities.

    `odds` must have columns ``b365_home``, ``b365_draw`` and ``b365_away``. The raw
    inverse-odds normally sum to >1 (the bookmaker's margin / overround); scaling each
    row to sum to 1 removes that margin, which is the simplest unbiased conversion.
    """
    required = ("b365_home", "b365_draw", "b365_away")
    missing = [column for column in required if column not in odds.columns]
    if missing:
        raise KeyError(f"Missing odds columns: {missing}")

    inverse = 1.0 / odds[list(required)].astype(float).to_numpy()
    totals = inverse.sum(axis=1, keepdims=True)
    return inverse / totals

"""Train and evaluate the pre-match prediction models end-to-end.

Reads every match out of the database, builds the training table, fits the baseline
logistic regression and the gradient boosting classifier, and writes three artefacts:

- `data/artifacts/logistic_regression.joblib` — fitted sklearn pipeline
- `data/artifacts/gradient_boosting.joblib`   — fitted sklearn pipeline
- `data/artifacts/predictions.csv`            — one row per test match, with the
  probabilities each baseline and model predicted plus the true outcome
- `data/artifacts/metrics.json`               — accuracy and log loss per model

Train/test split: the test set is the 2015/16 season (the demo season), which is
also the season that overlaps with StatsBomb's open event data. Everything before
is training data.

Usage (from backend/):
    uv run python -m pitchsense.ml.train --out ../data/artifacts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from pitchsense.db.session import get_engine
from pitchsense.ml.baselines import always_home_probabilities, bet365_implied_probabilities
from pitchsense.ml.evaluation import Metrics, evaluate
from pitchsense.ml.features import FEATURE_COLUMNS, build_training_table
from pitchsense.ml.models import make_gradient_boosting, make_logistic_regression

logger = logging.getLogger(__name__)

TEST_SEASON = "2015/2016"
MIN_TRAIN_SIZE = 500  # sanity check; the real dataset gives >20k


@dataclass(frozen=True, slots=True)
class SplitResult:
    train: pd.DataFrame
    test: pd.DataFrame


def split_by_season(table: pd.DataFrame, test_season: str = TEST_SEASON) -> SplitResult:
    """Everything strictly before `test_season` becomes training; `test_season` is held out."""
    if test_season not in set(table["season"]):
        raise ValueError(f"Season {test_season!r} not present in the data")
    train = table[table["season"] < test_season].reset_index(drop=True)
    test = table[table["season"] == test_season].reset_index(drop=True)
    return SplitResult(train=train, test=test)


def _odds_available(df: pd.DataFrame) -> pd.Series:
    """Mask of rows with a complete Bet365 H/D/A triple, needed for the odds baseline."""
    return df[["b365_home", "b365_draw", "b365_away"]].notna().all(axis=1)


def build_predictions_frame(
    test: pd.DataFrame,
    lr_probs: np.ndarray,
    gb_probs: np.ndarray,
) -> pd.DataFrame:
    """Return one row per test match with the actual outcome and each model's probabilities."""
    out = test[
        [
            "match_api_id",
            "league_id",
            "season",
            "match_date",
            "home_team_api_id",
            "away_team_api_id",
            "home_goals",
            "away_goals",
            "outcome",
            "b365_home",
            "b365_draw",
            "b365_away",
        ]
    ].copy()

    home_baseline = always_home_probabilities(len(test))
    out["home_baseline_h"] = home_baseline[:, 0]
    out["home_baseline_d"] = home_baseline[:, 1]
    out["home_baseline_a"] = home_baseline[:, 2]

    odds_mask = _odds_available(test)
    odds_probs = np.full((len(test), 3), np.nan)
    if odds_mask.any():
        odds_probs[odds_mask.to_numpy()] = bet365_implied_probabilities(test.loc[odds_mask])
    out["odds_baseline_h"] = odds_probs[:, 0]
    out["odds_baseline_d"] = odds_probs[:, 1]
    out["odds_baseline_a"] = odds_probs[:, 2]

    out["lr_h"] = lr_probs[:, 0]
    out["lr_d"] = lr_probs[:, 1]
    out["lr_a"] = lr_probs[:, 2]

    out["gb_h"] = gb_probs[:, 0]
    out["gb_d"] = gb_probs[:, 1]
    out["gb_a"] = gb_probs[:, 2]
    return out


@dataclass(frozen=True, slots=True)
class TrainingResult:
    predictions: pd.DataFrame
    metrics: dict[str, Metrics]
    logistic_regression: object
    gradient_boosting: object


def train(table: pd.DataFrame, test_season: str = TEST_SEASON) -> TrainingResult:
    """Fit both models on `table` split by season and report all baseline comparisons."""
    split = split_by_season(table, test_season)
    if len(split.train) < MIN_TRAIN_SIZE:
        raise ValueError(
            f"Only {len(split.train)} training matches; need at least {MIN_TRAIN_SIZE}"
        )

    logger.info("Training on %d matches, testing on %d", len(split.train), len(split.test))

    x_train = split.train[FEATURE_COLUMNS].to_numpy()
    y_train = split.train["outcome"].to_numpy()
    x_test = split.test[FEATURE_COLUMNS].to_numpy()
    y_test = split.test["outcome"].to_numpy()

    lr = make_logistic_regression()
    lr.fit(x_train, y_train)
    lr_probs = lr.predict_proba(x_test)

    gb = make_gradient_boosting()
    gb.fit(x_train, y_train)
    gb_probs = gb.predict_proba(x_test)

    home_probs = always_home_probabilities(len(split.test))
    odds_mask = _odds_available(split.test)
    odds_test = split.test.loc[odds_mask]
    odds_probs = bet365_implied_probabilities(odds_test) if len(odds_test) > 0 else np.empty((0, 3))

    metrics: dict[str, Metrics] = {
        "always_home": evaluate(y_test, home_probs),
        "logistic_regression": evaluate(y_test, lr_probs),
        "gradient_boosting": evaluate(y_test, gb_probs),
    }
    if len(odds_test) > 0:
        metrics["bet365_odds"] = evaluate(odds_test["outcome"].to_numpy(), odds_probs)

    predictions = build_predictions_frame(split.test, lr_probs, gb_probs)
    return TrainingResult(
        predictions=predictions,
        metrics=metrics,
        logistic_regression=lr,
        gradient_boosting=gb,
    )


def save_artifacts(result: TrainingResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(result.logistic_regression, output_dir / "logistic_regression.joblib")
    joblib.dump(result.gradient_boosting, output_dir / "gradient_boosting.joblib")
    result.predictions.to_csv(output_dir / "predictions.csv", index=False)
    (output_dir / "metrics.json").write_text(
        json.dumps(
            {name: m.as_dict() for name, m in result.metrics.items()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def print_metrics(metrics: dict[str, Metrics]) -> None:
    print(f"{'model':<24} {'accuracy':>10} {'log_loss':>10} {'n':>8}")
    print("-" * 56)
    for name, m in metrics.items():
        print(f"{name:<24} {m.accuracy:>10.4f} {m.log_loss:>10.4f} {m.n_samples:>8}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../data/artifacts"),
        help="Where to write the model, predictions and metrics artifacts",
    )
    parser.add_argument(
        "--test-season",
        default=TEST_SEASON,
        help='Season to hold out as the test set (default: "2015/2016")',
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log progress")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine = get_engine()
    with Session(engine) as session:
        table = build_training_table(session)

    if table.empty:
        print("No training data available — did the ETL run?", file=sys.stderr)
        return 1

    result = train(table, test_season=args.test_season)
    save_artifacts(result, args.out)
    print_metrics(result.metrics)
    print(f"\nArtifacts written to {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

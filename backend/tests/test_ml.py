"""Tests for the ML pipeline: features, baselines, models, evaluation and splitting."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pitchsense.ml.baselines import always_home_probabilities, bet365_implied_probabilities
from pitchsense.ml.evaluation import evaluate
from pitchsense.ml.features import (
    FEATURE_COLUMNS,
    Outcome,
    compute_form_features,
    compute_h2h_features,
    compute_outcome,
)
from pitchsense.ml.models import make_gradient_boosting, make_logistic_regression
from pitchsense.ml.train import split_by_season

# ----- synthetic data helper ---------------------------------------------------------


def synthetic_matches(n_pairs: int = 8) -> pd.DataFrame:
    """Return a tidy matches DataFrame with two teams meeting repeatedly.

    Home team wins every match 2-0, so form and h2h should predict home-win cleanly.
    """
    start = date(2015, 1, 1)
    rows = []
    for i in range(n_pairs):
        rows.append(
            {
                "match_api_id": 1000 + i,
                "league_id": 1,
                "season": "2015/2016" if i < n_pairs - 2 else "2016/2017",
                "match_date": start + timedelta(days=14 * i),
                "home_team_api_id": 10 if i % 2 == 0 else 20,
                "away_team_api_id": 20 if i % 2 == 0 else 10,
                "home_goals": 2,
                "away_goals": 0,
                "b365_home": 1.5,
                "b365_draw": 4.0,
                "b365_away": 6.0,
            }
        )
    df = pd.DataFrame(rows)
    df["match_date"] = pd.to_datetime(df["match_date"])
    df["outcome"] = compute_outcome(df["home_goals"], df["away_goals"])
    return df


# ----- features.py -------------------------------------------------------------------


def test_compute_outcome_classifies_each_result() -> None:
    home = pd.Series([2, 1, 0])
    away = pd.Series([0, 1, 3])
    result = compute_outcome(home, away)

    assert list(result) == [int(Outcome.HOME_WIN), int(Outcome.DRAW), int(Outcome.AWAY_WIN)]


def test_form_features_exclude_current_match(tmp_path: object) -> None:
    matches = synthetic_matches(n_pairs=6)

    form = compute_form_features(matches)

    # First meeting: no prior data, so ppg_last5 must be NaN.
    first = form[form["match_api_id"] == 1000].iloc[0]
    assert pd.isna(first["home_ppg_last5"])
    assert pd.isna(first["away_ppg_last5"])

    # Second meeting: team 10 had one win = 3 points; so its last-5 PPG is 3.0.
    second = form[form["match_api_id"] == 1001].iloc[0]
    # Team 10 is now AWAY for match 1001 (odd index in our fixture), had 1 win last time
    assert second["away_ppg_last5"] == pytest.approx(3.0)


def test_h2h_tracks_previous_meetings() -> None:
    matches = synthetic_matches(n_pairs=6)

    h2h = compute_h2h_features(matches)

    # First meeting: no prior h2h
    first = h2h[h2h["match_api_id"] == 1000].iloc[0]
    assert pd.isna(first["h2h_home_win_rate"])

    # Third meeting is 1002 — team 10 home again. Prior record vs team 20:
    # won 1000 at home, lost 1001 away. So h2h is 1W-1L from home-team view.
    third = h2h[h2h["match_api_id"] == 1002].iloc[0]
    assert third["h2h_home_win_rate"] == pytest.approx(0.5)
    assert third["h2h_away_win_rate"] == pytest.approx(0.5)


# ----- baselines.py ------------------------------------------------------------------


def test_always_home_puts_all_mass_on_class_zero() -> None:
    probs = always_home_probabilities(4)

    assert probs.shape == (4, 3)
    assert (probs[:, 0] == 1.0).all()
    assert (probs[:, 1:] == 0.0).all()


def test_bet365_implied_probabilities_normalise_to_one() -> None:
    odds = pd.DataFrame({"b365_home": [1.5, 2.0], "b365_draw": [4.0, 3.5], "b365_away": [6.0, 4.0]})

    probs = bet365_implied_probabilities(odds)

    assert probs.shape == (2, 3)
    assert np.allclose(probs.sum(axis=1), 1.0)
    # Shorter home odds → higher implied probability on home.
    assert (probs[:, 0] > probs[:, 2]).all()


def test_bet365_implied_raises_when_odds_missing() -> None:
    with pytest.raises(KeyError):
        bet365_implied_probabilities(pd.DataFrame({"b365_home": [1.5]}))


# ----- models.py ---------------------------------------------------------------------


def test_logistic_pipeline_handles_missing_values() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(size=(40, len(FEATURE_COLUMNS)))
    x[0, 0] = np.nan  # ensure the imputer runs
    y = rng.integers(0, 3, size=40)

    pipeline = make_logistic_regression()
    pipeline.fit(x, y)
    probs = pipeline.predict_proba(x)

    assert probs.shape == (40, 3)
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_gradient_boosting_pipeline_fits() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(size=(40, len(FEATURE_COLUMNS)))
    y = rng.integers(0, 3, size=40)

    pipeline = make_gradient_boosting()
    pipeline.fit(x, y)
    probs = pipeline.predict_proba(x)

    assert probs.shape == (40, 3)


# ----- evaluation.py -----------------------------------------------------------------


def test_evaluate_scores_perfect_prediction() -> None:
    y_true = np.array([0, 1, 2, 0])
    perfect = np.eye(3)[y_true]  # one-hot
    almost = perfect * 0.9 + 0.05  # clip-safe near-perfect

    metrics = evaluate(y_true, almost)

    assert metrics.accuracy == 1.0
    assert metrics.log_loss < 0.2
    assert metrics.n_samples == 4


def test_evaluate_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        evaluate(np.array([0, 1]), np.array([[0.5, 0.5]]))  # 2 cols, not 3


# ----- train.split_by_season ---------------------------------------------------------


def test_split_by_season_holds_out_the_target_season() -> None:
    matches = synthetic_matches(n_pairs=6)
    matches = matches.assign(**{col: 1.0 for col in FEATURE_COLUMNS})

    split = split_by_season(matches, "2016/2017")

    assert set(split.train["season"]) == {"2015/2016"}
    assert set(split.test["season"]) == {"2016/2017"}


def test_split_by_season_rejects_unknown_season() -> None:
    matches = synthetic_matches(n_pairs=4)

    with pytest.raises(ValueError):
        split_by_season(matches, "2099/2100")

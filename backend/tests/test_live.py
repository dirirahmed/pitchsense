"""Unit tests for the Monte Carlo engine and clutch-moment detector."""

from __future__ import annotations

import numpy as np
import pytest

from pitchsense.live.clutch import detect_clutch
from pitchsense.live.engine import (
    HOME_GOALS_PER_MATCH,
    MATCH_MINUTES,
    MatchState,
    WinProbabilities,
    simulate,
)

# ---- engine --------------------------------------------------------------------------


def test_simulate_returns_a_valid_probability_distribution() -> None:
    probs = simulate(MatchState(minute=0, home_score=0, away_score=0), n_simulations=5000)

    assert 0.0 <= probs.home <= 1.0
    assert 0.0 <= probs.draw <= 1.0
    assert 0.0 <= probs.away <= 1.0
    assert probs.home + probs.draw + probs.away == pytest.approx(1.0, abs=1e-9)


def test_simulate_from_kickoff_favours_home_team() -> None:
    probs = simulate(
        MatchState(minute=0, home_score=0, away_score=0),
        n_simulations=10_000,
        rng=np.random.default_rng(1),
    )

    # ESD averages have the home team scoring ~0.3 more goals per match.
    assert probs.home > probs.away


def test_leading_at_halftime_improves_home_probability() -> None:
    kickoff = simulate(
        MatchState(minute=0, home_score=0, away_score=0),
        n_simulations=10_000,
        rng=np.random.default_rng(2),
    )
    leading = simulate(
        MatchState(minute=45, home_score=1, away_score=0),
        n_simulations=10_000,
        rng=np.random.default_rng(2),
    )

    assert leading.home > kickoff.home + 0.1


def test_red_card_against_home_hurts_home() -> None:
    clean = simulate(
        MatchState(minute=60, home_score=0, away_score=0),
        n_simulations=10_000,
        rng=np.random.default_rng(3),
    )
    red = simulate(
        MatchState(minute=60, home_score=0, away_score=0, home_red_cards=1),
        n_simulations=10_000,
        rng=np.random.default_rng(3),
    )

    assert red.home < clean.home
    assert red.away > clean.away


def test_full_time_returns_degenerate_distribution() -> None:
    probs = simulate(MatchState(minute=MATCH_MINUTES, home_score=2, away_score=1))

    assert probs == WinProbabilities(home=1.0, draw=0.0, away=0.0)


def test_full_time_draw_concentrates_on_draw() -> None:
    probs = simulate(MatchState(minute=MATCH_MINUTES, home_score=1, away_score=1))

    assert probs == WinProbabilities(home=0.0, draw=1.0, away=0.0)


def test_rates_scale_with_match_length() -> None:
    """Expected goals when scaled up still correspond roughly to the ESD home average."""
    rng = np.random.default_rng(42)
    state = MatchState(minute=0, home_score=0, away_score=0)
    homes = [simulate(state, n_simulations=1000, rng=rng).home for _ in range(5)]
    mean_home = float(np.mean(homes))
    # Not a precise claim; just a sanity check that the simulation isn't absurd.
    assert HOME_GOALS_PER_MATCH > 1.0
    assert 0.3 < mean_home < 0.7


# ---- clutch --------------------------------------------------------------------------


def test_detect_clutch_flags_big_home_swing() -> None:
    before = WinProbabilities(0.30, 0.30, 0.40)
    after = WinProbabilities(0.60, 0.20, 0.20)

    result = detect_clutch(before, after)

    assert result is not None
    assert result.beneficiary == "home"
    assert result.swing_home_pp == pytest.approx(0.30)
    assert result.swing_away_pp == pytest.approx(-0.20)


def test_detect_clutch_flags_big_away_swing() -> None:
    before = WinProbabilities(0.60, 0.20, 0.20)
    after = WinProbabilities(0.30, 0.20, 0.50)

    result = detect_clutch(before, after)

    assert result is not None
    assert result.beneficiary == "away"


def test_detect_clutch_ignores_small_swings() -> None:
    before = WinProbabilities(0.45, 0.25, 0.30)
    after = WinProbabilities(0.50, 0.25, 0.25)

    assert detect_clutch(before, after) is None


def test_detect_clutch_threshold_is_configurable() -> None:
    before = WinProbabilities(0.45, 0.25, 0.30)
    after = WinProbabilities(0.55, 0.25, 0.20)

    assert detect_clutch(before, after, threshold=0.05) is not None
    assert detect_clutch(before, after, threshold=0.20) is None

"""Monte Carlo win probability engine for a live or replayed match.

For every recalculation we run `N_SIMULATIONS` independent simulations: each draws
the number of remaining home and away goals from independent Poisson distributions
and adds them to the current score. The share of simulations that end in a home
win, draw or away win is the predicted probability.

Baseline goal rates come from the ESD historical averages, scaled per-minute.
Red cards reduce the offending team's expected remaining goals by a configurable
multiplier.

The design intentionally stays simple: no tactical or "momentum" inventions.
Everything that moves the probability is stated, measurable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

MATCH_MINUTES: Final = 90
# ESD 2008-2016 averages: 1.54 home goals, 1.21 away goals per match.
HOME_GOALS_PER_MATCH: Final = 1.54
AWAY_GOALS_PER_MATCH: Final = 1.21
# After a red card, the affected team's remaining goal rate is multiplied by this.
# Derived from inspection of matches with red cards (rough estimate; will be
# re-measured once red-card events are ingested).
RED_CARD_RATE_MULTIPLIER: Final = 0.70
N_SIMULATIONS: Final = 10_000


@dataclass(frozen=True, slots=True)
class MatchState:
    """A snapshot of the current state the live engine needs to re-forecast from."""

    minute: int
    home_score: int
    away_score: int
    home_red_cards: int = 0
    away_red_cards: int = 0


@dataclass(frozen=True, slots=True)
class WinProbabilities:
    home: float
    draw: float
    away: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.home, self.draw, self.away)


def _remaining_rate(base_per_match: float, red_cards: int, minutes_remaining: float) -> float:
    """Expected remaining goals, scaled by minutes left and reduced for each red card."""
    per_minute = base_per_match / MATCH_MINUTES
    penalty = RED_CARD_RATE_MULTIPLIER**red_cards
    return per_minute * penalty * minutes_remaining


def simulate(
    state: MatchState,
    n_simulations: int = N_SIMULATIONS,
    rng: np.random.Generator | None = None,
) -> WinProbabilities:
    """Return W/D/L probabilities for the given match state.

    Full-time (minute >= 90) returns a degenerate distribution on the actual result.
    """
    if state.minute >= MATCH_MINUTES:
        if state.home_score > state.away_score:
            return WinProbabilities(1.0, 0.0, 0.0)
        if state.home_score < state.away_score:
            return WinProbabilities(0.0, 0.0, 1.0)
        return WinProbabilities(0.0, 1.0, 0.0)

    if rng is None:
        rng = np.random.default_rng()

    minutes_remaining = float(MATCH_MINUTES - state.minute)
    home_rate = _remaining_rate(HOME_GOALS_PER_MATCH, state.home_red_cards, minutes_remaining)
    away_rate = _remaining_rate(AWAY_GOALS_PER_MATCH, state.away_red_cards, minutes_remaining)

    home_sim_goals = rng.poisson(lam=home_rate, size=n_simulations)
    away_sim_goals = rng.poisson(lam=away_rate, size=n_simulations)

    final_home = state.home_score + home_sim_goals
    final_away = state.away_score + away_sim_goals

    home_wins = int(np.sum(final_home > final_away))
    draws = int(np.sum(final_home == final_away))
    away_wins = n_simulations - home_wins - draws

    return WinProbabilities(
        home=home_wins / n_simulations,
        draw=draws / n_simulations,
        away=away_wins / n_simulations,
    )

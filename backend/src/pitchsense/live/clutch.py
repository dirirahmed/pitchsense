"""Clutch-moment detection.

A clutch moment is an event whose probability update swings the win probability for
either team by more than `THRESHOLD_PP` percentage points. The default 15 pp matches
the project brief; expose it as an argument so research can tune it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pitchsense.live.engine import WinProbabilities

THRESHOLD_PP: Final = 0.15


@dataclass(frozen=True, slots=True)
class ClutchResult:
    """Attached to any event whose swing crosses the threshold."""

    swing_home_pp: float
    swing_away_pp: float
    beneficiary: str  # "home" or "away"


def detect_clutch(
    before: WinProbabilities,
    after: WinProbabilities,
    threshold: float = THRESHOLD_PP,
) -> ClutchResult | None:
    """Return a ClutchResult if the home or away probability moved by >= threshold."""
    swing_home = after.home - before.home
    swing_away = after.away - before.away
    if abs(swing_home) < threshold and abs(swing_away) < threshold:
        return None
    # Beneficiary is whichever side gained the most from this event.
    beneficiary = "home" if swing_home >= swing_away else "away"
    return ClutchResult(
        swing_home_pp=swing_home,
        swing_away_pp=swing_away,
        beneficiary=beneficiary,
    )

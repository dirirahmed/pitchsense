"""Parse the ESD `Match.goal` XML column into (minute, scoring_team) events.

The XML looks like this per goal::

    <goal>
      <value>
        <stats><goals>1</goals></stats>
        <event_incident_typefk>406</event_incident_typefk>
        <elapsed>18</elapsed>
        <team>8650</team>
      </value>
      ...
    </goal>

We're interested in `elapsed` (the minute) and `team` (which team scored).
Own-goals exist but are rare enough that we treat them like regular goals attributed
to the scoring team; the ESD field already encodes that correctly.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET  # standard alias used across the project
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GoalEvent:
    """One goal event parsed from the source XML."""

    minute: int
    team_api_id: int

    def side(self, home_team_api_id: int) -> str:
        return "home" if self.team_api_id == home_team_api_id else "away"


def _parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def parse_goal_xml(xml_text: str | None) -> list[GoalEvent]:
    """Return a list of goal events parsed from ESD's goal XML column.

    Returns an empty list for None, empty, malformed or placeholder XML. A missing
    `elapsed` or `team` for one entry is skipped rather than aborting the whole match.
    """
    if not xml_text or not xml_text.strip() or xml_text.strip() == "<goal />":
        return []

    try:
        root = ET.fromstring(xml_text)  # ESD XML is local data, not user input
    except ET.ParseError as error:
        logger.warning("Could not parse goal XML: %s", error)
        return []

    events: list[GoalEvent] = []
    for value in root.findall("./value"):
        minute = _parse_int(value.findtext("elapsed"))
        team = _parse_int(value.findtext("team"))
        if minute is None or team is None:
            continue
        events.append(GoalEvent(minute=minute, team_api_id=team))

    return sorted(events, key=lambda event: event.minute)


def goals_match_score(
    goals: Iterable[GoalEvent],
    home_team_api_id: int,
    expected_home: int,
    expected_away: int,
) -> bool:
    """Sanity check: parsed events should sum to the recorded final score."""
    home = 0
    away = 0
    for event in goals:
        if event.team_api_id == home_team_api_id:
            home += 1
        else:
            away += 1
    return home == expected_home and away == expected_away

"""Unit tests for ESD goal-XML parsing."""

from __future__ import annotations

import pytest

from pitchsense.etl.goal_events import GoalEvent, goals_match_score, parse_goal_xml

SAMPLE_XML = """<goal>
  <value>
    <stats><goals>1</goals></stats>
    <event_incident_typefk>406</event_incident_typefk>
    <elapsed>18</elapsed>
    <team>10</team>
  </value>
  <value>
    <stats><goals>1</goals></stats>
    <event_incident_typefk>406</event_incident_typefk>
    <elapsed>72</elapsed>
    <team>20</team>
  </value>
</goal>"""


def test_parse_goal_xml_returns_sorted_events() -> None:
    events = parse_goal_xml(SAMPLE_XML)

    assert events == [GoalEvent(minute=18, team_api_id=10), GoalEvent(minute=72, team_api_id=20)]


@pytest.mark.parametrize("value", [None, "", "   ", "<goal />"])
def test_parse_goal_xml_handles_empty_input(value: str | None) -> None:
    assert parse_goal_xml(value) == []


def test_parse_goal_xml_skips_entries_without_minute_or_team() -> None:
    xml = """<goal>
      <value><stats><goals>1</goals></stats><elapsed>12</elapsed></value>
      <value><stats><goals>1</goals></stats><team>42</team></value>
      <value><stats><goals>1</goals></stats><elapsed>88</elapsed><team>42</team></value>
    </goal>"""

    events = parse_goal_xml(xml)

    assert events == [GoalEvent(minute=88, team_api_id=42)]


def test_parse_goal_xml_returns_empty_on_malformed_input() -> None:
    assert parse_goal_xml("<goal><bad") == []


def test_side_from_home_team_id() -> None:
    event = GoalEvent(minute=10, team_api_id=10)

    assert event.side(home_team_api_id=10) == "home"
    assert event.side(home_team_api_id=20) == "away"


def test_goals_match_score_passes_matching_counts() -> None:
    events = [GoalEvent(minute=12, team_api_id=1), GoalEvent(minute=80, team_api_id=2)]

    assert goals_match_score(events, home_team_api_id=1, expected_home=1, expected_away=1)
    assert not goals_match_score(events, home_team_api_id=1, expected_home=2, expected_away=0)

"""Integration tests for the matches, predictions and replay endpoints.

Seeds a tiny slice of the schema, hits each endpoint via httpx TestClient, and
asserts the shape of the responses. The schema is already migrated by Alembic.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table
from sqlalchemy.orm import Session

from pitchsense.db.models import (
    Country,
    League,
    Match,
    MatchGoal,
    Prediction,
    Team,
)
from pitchsense.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def clean_engine() -> Iterator[Engine]:
    engine = get_engine()
    tables = (MatchGoal, Prediction, Match, Team, League, Country)

    def truncate() -> None:
        with engine.begin() as connection:
            for model in tables:
                connection.execute(cast(Table, model.__table__).delete())

    truncate()
    yield engine
    truncate()


@pytest.fixture
def seeded_match(clean_engine: Engine) -> int:
    """Insert a minimal country/league/teams/match/prediction graph; return match_api_id."""
    with Session(clean_engine) as session:
        session.add(Country(id=1, name="England"))
        session.add(League(id=1, country_id=1, name="England Premier League"))
        session.add(Team(team_api_id=10, long_name="Arsenal", short_name="ARS"))
        session.add(Team(team_api_id=20, long_name="Chelsea", short_name="CHE"))
        session.flush()
        session.add(
            Match(
                match_api_id=501,
                league_id=1,
                season="2015/2016",
                match_date=date(2015, 8, 8),
                stage=1,
                home_team_api_id=10,
                away_team_api_id=20,
                home_goals=2,
                away_goals=1,
            )
        )
        session.add(
            Prediction(
                match_api_id=501,
                home_baseline_h=1.0,
                home_baseline_d=0.0,
                home_baseline_a=0.0,
                odds_baseline_h=0.55,
                odds_baseline_d=0.25,
                odds_baseline_a=0.20,
                lr_h=0.48,
                lr_d=0.27,
                lr_a=0.25,
                gb_h=0.52,
                gb_d=0.24,
                gb_a=0.24,
            )
        )
        session.add(MatchGoal(match_api_id=501, minute=18, team_api_id=10))
        session.add(MatchGoal(match_api_id=501, minute=55, team_api_id=20))
        session.add(MatchGoal(match_api_id=501, minute=80, team_api_id=10))
        session.commit()
    return 501


@pytest.fixture
def app() -> FastAPI:
    from pitchsense.api.main import create_app

    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


# ---- /matches ------------------------------------------------------------------------


def test_list_matches_returns_seeded_match(seeded_match: int, client: TestClient) -> None:
    response = client.get("/matches", params={"season": "2015/2016"})

    assert response.status_code == 200
    body = response.json()
    assert body["season"] == "2015/2016"
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["match_api_id"] == seeded_match
    assert match["home"]["long_name"] == "Arsenal"
    assert match["away"]["long_name"] == "Chelsea"
    assert match["home_goals"] == 2
    assert match["away_goals"] == 1


def test_list_matches_filters_by_league(seeded_match: int, client: TestClient) -> None:
    on = client.get("/matches", params={"season": "2015/2016", "league_id": 1}).json()
    off = client.get("/matches", params={"season": "2015/2016", "league_id": 999}).json()

    assert len(on["matches"]) == 1
    assert off["matches"] == []


def test_get_match_returns_detail(seeded_match: int, client: TestClient) -> None:
    response = client.get(f"/matches/{seeded_match}")

    assert response.status_code == 200
    assert response.json()["match_api_id"] == seeded_match


def test_get_match_404_for_unknown_id(clean_engine: Engine, client: TestClient) -> None:
    response = client.get("/matches/999999")

    assert response.status_code == 404


# ---- /matches/{id}/prediction --------------------------------------------------------


def test_get_prediction_returns_all_four(seeded_match: int, client: TestClient) -> None:
    response = client.get(f"/matches/{seeded_match}/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["always_home_baseline"] == {"home": 1.0, "draw": 0.0, "away": 0.0}
    assert body["bet365_odds_baseline"]["home"] == 0.55
    assert body["logistic_regression"]["home"] == 0.48
    assert body["gradient_boosting"]["home"] == 0.52


def test_get_prediction_404_when_missing(clean_engine: Engine, client: TestClient) -> None:
    response = client.get("/matches/404404/prediction")

    assert response.status_code == 404


# ---- WebSocket /ws/matches/{id}/replay -----------------------------------------------


def test_replay_streams_state_goals_and_final(seeded_match: int, client: TestClient) -> None:
    with client.websocket_connect(
        f"/ws/matches/{seeded_match}/replay?seconds_per_minute=0"
    ) as websocket:
        messages = []
        while True:
            message = websocket.receive_json()
            messages.append(message)
            if message["type"] == "final":
                break

    types = [m["type"] for m in messages]
    assert types[0] == "state"
    # Three goals in the fixture → three goal messages.
    assert types.count("goal") == 3
    # One opening probability snapshot plus one per goal.
    assert types.count("probability") == 4
    final = messages[-1]
    assert final["home_score"] == 2
    assert final["away_score"] == 1


def test_replay_reports_error_for_unknown_match(client: TestClient) -> None:
    with client.websocket_connect("/ws/matches/999999/replay?seconds_per_minute=0") as websocket:
        message = websocket.receive_json()
        assert message == {"type": "error", "message": "match not found"}

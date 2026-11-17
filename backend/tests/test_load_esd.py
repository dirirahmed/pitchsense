"""Integration tests for the ESD loader, exercised against a real PostgreSQL."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine, Table, text
from sqlalchemy.orm import Session

from pitchsense.db.models import (
    Base,
    Country,
    League,
    Match,
    MatchLineup,
    Player,
    PlayerRating,
    Team,
)
from pitchsense.db.session import get_engine
from pitchsense.etl.load_esd import load_all

pytestmark = pytest.mark.integration

SCHEMA = """
CREATE TABLE Country (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE League (id INTEGER PRIMARY KEY, country_id INTEGER, name TEXT);
CREATE TABLE Team (
    id INTEGER PRIMARY KEY, team_api_id INTEGER UNIQUE,
    team_long_name TEXT, team_short_name TEXT
);
CREATE TABLE Player (
    id INTEGER PRIMARY KEY, player_api_id INTEGER UNIQUE, player_name TEXT,
    birthday TEXT, height REAL, weight INTEGER
);
CREATE TABLE Player_Attributes (
    id INTEGER PRIMARY KEY, player_api_id INTEGER, date TEXT, overall_rating INTEGER
);
CREATE TABLE Match (
    id INTEGER PRIMARY KEY, country_id INTEGER, league_id INTEGER, season TEXT,
    stage INTEGER, date TEXT, match_api_id INTEGER UNIQUE,
    home_team_api_id INTEGER, away_team_api_id INTEGER,
    home_team_goal INTEGER, away_team_goal INTEGER,
    home_player_1 INTEGER, home_player_2 INTEGER, home_player_3 INTEGER, home_player_4 INTEGER,
    home_player_5 INTEGER, home_player_6 INTEGER, home_player_7 INTEGER, home_player_8 INTEGER,
    home_player_9 INTEGER, home_player_10 INTEGER, home_player_11 INTEGER,
    away_player_1 INTEGER, away_player_2 INTEGER, away_player_3 INTEGER, away_player_4 INTEGER,
    away_player_5 INTEGER, away_player_6 INTEGER, away_player_7 INTEGER, away_player_8 INTEGER,
    away_player_9 INTEGER, away_player_10 INTEGER, away_player_11 INTEGER,
    B365H REAL, B365D REAL, B365A REAL
);
"""


def make_player_tuple(player_api_id: int, name: str) -> tuple[object, ...]:
    return (player_api_id, player_api_id, name, "1990-01-01 00:00:00", 180.0, 170)


@pytest.fixture
def source_sqlite(tmp_path: Path) -> Path:
    path = tmp_path / "esd.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO Country VALUES (1, 'England')")
    conn.execute("INSERT INTO League VALUES (1, 1, 'England Premier League')")
    conn.executemany(
        "INSERT INTO Team (team_api_id, team_long_name, team_short_name) VALUES (?, ?, ?)",
        [(10, "Arsenal", "ARS"), (20, "Chelsea", "CHE")],
    )
    conn.executemany(
        "INSERT INTO Player (player_api_id, player_name, birthday, height, weight) "
        "VALUES (?, ?, ?, ?, ?)",
        [make_player_tuple(i, f"Player {i}")[1:] for i in range(1, 25)],
    )
    # One player has two snapshots on the same date — the duplicate must be dropped.
    conn.executemany(
        "INSERT INTO Player_Attributes (player_api_id, date, overall_rating) VALUES (?, ?, ?)",
        [
            (1, "2015-08-01 00:00:00", 80),
            (1, "2015-08-01 00:00:00", 85),  # duplicate (player, date)
            (1, "2015-12-01 00:00:00", 82),
            (2, "2015-08-01 00:00:00", 75),
        ],
    )
    # Full lineup both sides
    full_lineup = tuple(range(1, 12)) + tuple(range(12, 23))
    # One side has a missing slot (NULL) → only 21 lineup rows instead of 22
    partial_lineup = (*range(1, 11), None, *range(12, 23))
    placeholders = ", ".join("?" * 22)
    conn.executemany(
        f"INSERT INTO Match VALUES (?, 1, 1, ?, ?, ?, ?, ?, ?, ?, ?, {placeholders}, ?, ?, ?)",
        [
            (
                1,
                "2015/2016",
                1,
                "2015-08-08 00:00:00",
                501,
                10,
                20,
                2,
                0,
                *full_lineup,
                1.5,
                4.0,
                6.0,
            ),
            (
                2,
                "2015/2016",
                2,
                "2015-08-15 00:00:00",
                502,
                20,
                10,
                1,
                1,
                *partial_lineup,
                None,
                None,
                None,  # no bookmaker odds
            ),
        ],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def clean_engine() -> Iterator[Engine]:
    """Return the real engine after resetting every ETL-managed table.

    Each test starts from an empty schema (migrations already applied) and leaves
    it that way too, so tests don't pollute real data in the dev database.
    """
    engine = get_engine()
    tables = (MatchLineup, PlayerRating, Match, Player, Team, League, Country)

    def truncate() -> None:
        with engine.begin() as connection:
            # Order matters: delete leaves before parents.
            for model in tables:
                connection.execute(cast(Table, model.__table__).delete())

    truncate()
    yield engine
    truncate()


def test_schema_is_migrated(clean_engine: Engine) -> None:
    """Sanity check: every model's table exists in the connected database."""
    with clean_engine.connect() as connection:
        for table in Base.metadata.tables:
            connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))


def test_load_counts_match_source(source_sqlite: Path, clean_engine: Engine) -> None:
    counts = load_all(source_sqlite, clean_engine)

    assert counts.countries == 1
    assert counts.leagues == 1
    assert counts.teams == 2
    assert counts.players == 24
    # 4 source rows, one is a duplicate (player, date), so 3 are inserted
    assert counts.player_ratings == 3
    assert counts.matches == 2
    # First match: 22 slots filled. Second match: 21 (one NULL dropped).
    assert counts.match_lineups == 43


def test_second_run_is_idempotent(source_sqlite: Path, clean_engine: Engine) -> None:
    load_all(source_sqlite, clean_engine)

    counts = load_all(source_sqlite, clean_engine)

    # All fresh inserts are skipped by ON CONFLICT DO NOTHING.
    assert counts == counts.__class__()


def test_odds_and_lineups_shape(source_sqlite: Path, clean_engine: Engine) -> None:
    load_all(source_sqlite, clean_engine)

    with Session(clean_engine) as session:
        # Primary key is match_api_id (501, 502 in the fixture), not the row id.
        match_one = session.get(Match, 501)
        assert match_one is not None
        assert match_one.season == "2015/2016"
        assert match_one.home_goals == 2 and match_one.away_goals == 0
        assert match_one.b365_home is not None and float(match_one.b365_home) == 1.5

        match_two = session.get(Match, 502)
        assert match_two is not None
        assert match_two.b365_home is None

        lineup_rows = session.execute(
            MatchLineup.__table__.select().where(MatchLineup.match_api_id == 502)
        ).all()
        # One slot was NULL in the source, so it must not be stored.
        assert len(lineup_rows) == 21


def test_player_rating_dedup_keeps_first(source_sqlite: Path, clean_engine: Engine) -> None:
    load_all(source_sqlite, clean_engine)

    with Session(clean_engine) as session:
        rating = session.execute(
            PlayerRating.__table__.select()
            .where(PlayerRating.player_api_id == 1)
            .where(PlayerRating.rating_date == __import__("datetime").date(2015, 8, 1))
        ).one()
    # Source had 80 then 85 for the duplicate; we keep the first (80).
    assert rating.overall_rating == 80

"""Tests for the ESD inspection report, using a small database shaped like the real one."""

import sqlite3
from pathlib import Path

import pytest

from pitchsense.etl.inspect_esd import bookmakers, build_report, connect_read_only, main

SCHEMA = """
CREATE TABLE Country (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE League (id INTEGER PRIMARY KEY, country_id INTEGER, name TEXT);
CREATE TABLE Team (id INTEGER PRIMARY KEY, team_api_id INTEGER, team_long_name TEXT);
CREATE TABLE Player (id INTEGER PRIMARY KEY, player_api_id INTEGER, player_name TEXT);
CREATE TABLE Player_Attributes (
    id INTEGER PRIMARY KEY, player_api_id INTEGER, date TEXT, overall_rating INTEGER
);
CREATE TABLE Match (
    id INTEGER PRIMARY KEY, country_id INTEGER, league_id INTEGER, season TEXT, date TEXT,
    match_api_id INTEGER, home_team_api_id INTEGER, away_team_api_id INTEGER,
    home_team_goal INTEGER, away_team_goal INTEGER,
    home_player_1 INTEGER, away_player_1 INTEGER,
    goal TEXT, card TEXT,
    B365H REAL, B365D REAL, B365A REAL
);
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "esd.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO Country VALUES (1, 'England')")
    conn.execute("INSERT INTO League VALUES (1, 1, 'England Premier League')")
    conn.executemany("INSERT INTO Team VALUES (?, ?, ?)", [(1, 10, "Arsenal"), (2, 20, "Chelsea")])
    conn.executemany("INSERT INTO Player VALUES (?, ?, ?)", [(1, 100, "A"), (2, 200, "B")])
    conn.executemany(
        "INSERT INTO Player_Attributes VALUES (?, ?, ?, ?)",
        [(1, 100, "2015-01-01", 80), (2, 100, "2015-06-01", 82), (3, 999, "2015-01-01", 70)],
    )
    conn.executemany(
        "INSERT INTO Match VALUES (?, 1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # Home win with full data
            (
                1,
                "2015/2016",
                "2015-08-08",
                501,
                10,
                20,
                2,
                0,
                100,
                200,
                "<goal/>",
                "",
                1.5,
                4.0,
                6.0,
            ),
            # Draw, missing odds and XML, unknown away player
            (
                2,
                "2015/2016",
                "2015-08-15",
                502,
                20,
                10,
                1,
                1,
                100,
                300,
                None,
                None,
                None,
                None,
                None,
            ),
            # Duplicate match_api_id with an unknown home team
            (
                3,
                "2014/2015",
                "2014-08-16",
                502,
                99,
                20,
                0,
                1,
                None,
                None,
                None,
                None,
                2.0,
                3.0,
                3.5,
            ),
        ],
    )
    conn.commit()
    conn.close()
    return path


def report_for(path: Path) -> str:
    conn = connect_read_only(path)
    try:
        return "\n".join(build_report(conn))
    finally:
        conn.close()


def test_report_lists_tables_and_seasons(database: Path) -> None:
    report = report_for(database)

    assert "| Match | 3 | 17 |" in report
    assert "- Total matches: 3" in report
    assert "| England Premier League | 1 | 2 | 3 |" in report


def test_report_detects_duplicates_and_orphans(database: Path) -> None:
    report = report_for(database)

    assert "- Duplicate `match_api_id` values: 1" in report
    assert "- `Match.home_team_api_id` not found in `Team`: 1" in report
    assert "- Lineup player ids not found in `Player` (across 2 columns): 1" in report
    assert "- `player_api_id` not found in `Player`: 1" in report


def test_report_measures_odds_and_xml_coverage(database: Path) -> None:
    report = report_for(database)

    # 2015/16: one of two matches has complete Bet365 odds
    assert "| 2015/2016 | 50.0% |" in report
    # Lineup ids filled in 2 of 3 matches; `goal` XML in 1 of 3; `card` only empty strings
    assert "| England Premier League | 3 | 66.7% | 33.3% | 0.0% |" in report


def test_bookmakers_requires_complete_triples(database: Path) -> None:
    conn = connect_read_only(database)
    try:
        assert bookmakers(conn) == ["B365"]
    finally:
        conn.close()


def test_database_is_opened_read_only(database: Path) -> None:
    conn = connect_read_only(database)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM Match")
    finally:
        conn.close()


def test_main_writes_report_file(database: Path, tmp_path: Path) -> None:
    output = tmp_path / "out" / "report.md"

    assert main([str(database), "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8").startswith("# European Soccer Database inspection")


def test_main_fails_cleanly_for_missing_file(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.sqlite")]) == 1

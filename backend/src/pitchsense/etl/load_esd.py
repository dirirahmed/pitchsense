"""Load the European Soccer Database into PostgreSQL.

Reads the ESD SQLite file (read-only) and writes to whichever PostgreSQL database
DATABASE_URL points at. Runs cleanly on a database that already holds the data:
every insert uses ON CONFLICT DO NOTHING, so a second run is a no-op.

Usage (from backend/):
    uv run alembic upgrade head
    uv run python -m pitchsense.etl.load_esd ../data/raw/database.sqlite
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from sqlalchemy import Engine, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
# Number of lineup slots per side in the source. See data/esd_inspection.md.
LINEUP_SLOTS = range(1, 12)


# --- type aliases and parsing helpers ---------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadCounts:
    countries: int = 0
    leagues: int = 0
    teams: int = 0
    players: int = 0
    player_ratings: int = 0
    matches: int = 0
    match_lineups: int = 0

    def summary(self) -> str:
        return (
            f"countries={self.countries} leagues={self.leagues} teams={self.teams} "
            f"players={self.players} player_ratings={self.player_ratings} "
            f"matches={self.matches} match_lineups={self.match_lineups}"
        )


def parse_date(value: str | None) -> date | None:
    """ESD dates look like '2016-05-25 00:00:00'; ignore the trailing time."""
    if value is None:
        return None
    return datetime.fromisoformat(value).date()


def parse_optional_int(value: object) -> int | None:
    if value is None:
        return None
    # Some columns arrive as "182.88" (a string) for a height; float() handles both.
    if isinstance(value, int | float | str):
        return int(float(value))
    raise TypeError(f"Cannot convert {type(value).__name__} to int")


def parse_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def batched(rows: Iterable[dict[str, object]], size: int) -> Iterator[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# --- loader per table -------------------------------------------------------------


def connect_source(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def upsert(engine: Engine, model: type[Base], rows: Sequence[dict[str, object]]) -> int:
    """Insert rows, ignoring any that clash with a primary key or unique constraint.

    Returns the number of rows actually inserted (skipped rows don't count). We use
    RETURNING because psycopg reports -1 for ``rowcount`` on ON CONFLICT statements.
    """
    if not rows:
        return 0
    # SQLAlchemy's declarative base types __table__ as FromClause; downstream calls
    # (pg_insert, primary_key.columns, delete) need the concrete Table type.
    table = cast(Table, model.__table__)
    pk_column = next(iter(table.primary_key.columns))
    inserted = 0
    with engine.begin() as connection:
        for chunk in batched(rows, BATCH_SIZE):
            statement = pg_insert(table).values(chunk).on_conflict_do_nothing().returning(pk_column)
            result = connection.execute(statement)
            inserted += len(result.fetchall())
    return inserted


def load_countries(source: sqlite3.Connection, engine: Engine) -> int:
    rows = [
        {"id": row["id"], "name": row["name"]}
        for row in source.execute("SELECT id, name FROM Country")
    ]
    return upsert(engine, Country, rows)


def load_leagues(source: sqlite3.Connection, engine: Engine) -> int:
    rows = [
        {"id": row["id"], "country_id": row["country_id"], "name": row["name"]}
        for row in source.execute("SELECT id, country_id, name FROM League")
    ]
    return upsert(engine, League, rows)


def load_teams(source: sqlite3.Connection, engine: Engine) -> int:
    rows = [
        {
            "team_api_id": row["team_api_id"],
            "long_name": row["team_long_name"],
            "short_name": row["team_short_name"],
        }
        for row in source.execute("SELECT team_api_id, team_long_name, team_short_name FROM Team")
    ]
    return upsert(engine, Team, rows)


def load_players(source: sqlite3.Connection, engine: Engine) -> int:
    rows = [
        {
            "player_api_id": row["player_api_id"],
            "name": row["player_name"],
            "birthday": parse_date(row["birthday"]),
            "height_cm": parse_optional_int(row["height"]),
            "weight_lb": parse_optional_int(row["weight"]),
        }
        for row in source.execute(
            "SELECT player_api_id, player_name, birthday, height, weight FROM Player"
        )
    ]
    return upsert(engine, Player, rows)


def load_player_ratings(source: sqlite3.Connection, engine: Engine) -> int:
    """Load FIFA overall ratings; the source has ~835 duplicate (player, date) pairs.

    We keep the first one seen (ordered by `id`, i.e. insertion order in the source).
    """
    seen: set[tuple[int, date]] = set()
    rows: list[dict[str, object]] = []
    cursor = source.execute(
        "SELECT player_api_id, date, overall_rating FROM Player_Attributes "
        "WHERE overall_rating IS NOT NULL ORDER BY id"
    )
    for row in cursor:
        player_api_id = row["player_api_id"]
        rating_date = parse_date(row["date"])
        if rating_date is None:
            continue
        key = (player_api_id, rating_date)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "player_api_id": player_api_id,
                "rating_date": rating_date,
                "overall_rating": row["overall_rating"],
            }
        )
    return upsert(engine, PlayerRating, rows)


def match_rows(
    source: sqlite3.Connection,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return (match rows, lineup rows) parsed from the source Match table.

    The source stores 11 player ids per side as separate columns; this expands them
    into one row per (match, side, slot), skipping NULL slots.
    """
    match_cols = [
        "match_api_id",
        "league_id",
        "season",
        "date",
        "stage",
        "home_team_api_id",
        "away_team_api_id",
        "home_team_goal",
        "away_team_goal",
        "B365H",
        "B365D",
        "B365A",
    ]
    lineup_cols = [f"{side}_player_{slot}" for side in ("home", "away") for slot in LINEUP_SLOTS]
    all_cols = ", ".join(match_cols + lineup_cols)

    matches: list[dict[str, object]] = []
    lineups: list[dict[str, object]] = []
    for row in source.execute(f"SELECT {all_cols} FROM Match"):
        match_date = parse_date(row["date"])
        if match_date is None:
            continue
        matches.append(
            {
                "match_api_id": row["match_api_id"],
                "league_id": row["league_id"],
                "season": row["season"],
                "match_date": match_date,
                "stage": row["stage"],
                "home_team_api_id": row["home_team_api_id"],
                "away_team_api_id": row["away_team_api_id"],
                "home_goals": row["home_team_goal"],
                "away_goals": row["away_team_goal"],
                "b365_home": parse_optional_decimal(row["B365H"]),
                "b365_draw": parse_optional_decimal(row["B365D"]),
                "b365_away": parse_optional_decimal(row["B365A"]),
            }
        )
        for side in ("home", "away"):
            for slot in LINEUP_SLOTS:
                player_api_id = row[f"{side}_player_{slot}"]
                if player_api_id is None:
                    continue
                lineups.append(
                    {
                        "match_api_id": row["match_api_id"],
                        "side": side,
                        "slot": slot,
                        "player_api_id": player_api_id,
                    }
                )
    return matches, lineups


def load_matches_and_lineups(source: sqlite3.Connection, engine: Engine) -> tuple[int, int]:
    matches, lineups = match_rows(source)
    inserted_matches = upsert(engine, Match, matches)
    inserted_lineups = upsert(engine, MatchLineup, lineups)
    return inserted_matches, inserted_lineups


# --- CLI -------------------------------------------------------------------------


def load_all(source_path: Path, engine: Engine | None = None) -> LoadCounts:
    if engine is None:
        engine = get_engine()
    source = connect_source(source_path)
    try:
        logger.info("Loading countries...")
        countries = load_countries(source, engine)
        logger.info("Loading leagues...")
        leagues = load_leagues(source, engine)
        logger.info("Loading teams...")
        teams = load_teams(source, engine)
        logger.info("Loading players...")
        players = load_players(source, engine)
        logger.info("Loading player ratings...")
        ratings = load_player_ratings(source, engine)
        logger.info("Loading matches and lineups...")
        matches, lineups = load_matches_and_lineups(source, engine)
    finally:
        source.close()
    return LoadCounts(
        countries=countries,
        leagues=leagues,
        teams=teams,
        players=players,
        player_ratings=ratings,
        matches=matches,
        match_lineups=lineups,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("database", type=Path, help="Path to the ESD database.sqlite file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log each step")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.database.is_file():
        print(f"Database file not found: {args.database}", file=sys.stderr)
        return 1

    counts = load_all(args.database)
    print(counts.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

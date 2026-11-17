"""Parse ESD's `Match.goal` XML column and load the goal events into PostgreSQL.

Runs over every match in the source database; matches with empty/malformed XML
are reported but not treated as errors. Idempotent via a unique constraint on
(match_api_id, minute, team_api_id).

Usage (from backend/):
    uv run python -m pitchsense.etl.load_goals ../data/raw/database.sqlite
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from sqlalchemy import Engine, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pitchsense.db.models import MatchGoal
from pitchsense.db.session import get_engine
from pitchsense.etl.goal_events import goals_match_score, parse_goal_xml
from pitchsense.etl.load_esd import BATCH_SIZE, batched, connect_source

logger = logging.getLogger(__name__)


def collect_goal_rows(source: sqlite3.Connection) -> tuple[list[dict[str, object]], int, int]:
    """Return (rows, matches_with_events, matches_with_mismatched_score)."""
    cursor = source.execute(
        "SELECT match_api_id, home_team_api_id, away_team_api_id, "
        "       home_team_goal, away_team_goal, goal "
        "FROM Match"
    )
    rows: list[dict[str, object]] = []
    matches_with_events = 0
    mismatches = 0
    for match_api_id, home_team, away_team, home_score, away_score, xml in cursor:
        events = parse_goal_xml(xml)
        if not events:
            continue
        matches_with_events += 1
        if not goals_match_score(events, home_team, home_score, away_score):
            mismatches += 1
        for event in events:
            # Attribute goals only when the team id is one of the two playing.
            if event.team_api_id not in (home_team, away_team):
                continue
            rows.append(
                {
                    "match_api_id": match_api_id,
                    "minute": event.minute,
                    "team_api_id": event.team_api_id,
                }
            )
    return rows, matches_with_events, mismatches


def load_goals(source_path: Path, engine: Engine | None = None) -> tuple[int, int]:
    """Return (inserted_rows, matches_with_events)."""
    if engine is None:
        engine = get_engine()

    source = connect_source(source_path)
    try:
        rows, matches_with_events, mismatches = collect_goal_rows(source)
    finally:
        source.close()

    if mismatches:
        logger.warning(
            "%d matches had XML goal count disagreeing with final score (XML is incomplete)",
            mismatches,
        )

    if not rows:
        return 0, matches_with_events

    table = cast(Table, MatchGoal.__table__)
    inserted = 0
    with engine.begin() as connection:
        for chunk in batched(rows, BATCH_SIZE):
            statement = pg_insert(table).values(chunk).on_conflict_do_nothing()
            result = connection.execute(statement.returning(table.c.id))
            inserted += len(result.fetchall())
    return inserted, matches_with_events


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("database", type=Path, help="Path to the ESD database.sqlite file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.database.is_file():
        print(f"Database file not found: {args.database}", file=sys.stderr)
        return 1

    inserted, matches_with_events = load_goals(args.database)
    print(f"goals_inserted={inserted} matches_with_events={matches_with_events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

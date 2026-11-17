"""Inspect the Kaggle European Soccer Database before designing the ETL pipeline.

Produces a Markdown report of what the SQLite file actually contains: tables, columns,
null rates, coverage by league and season, duplicates and referential integrity.
The database is opened read-only.

Usage (from backend/):
    uv run python -m pitchsense.etl.inspect_esd ../data/raw/database.sqlite \
        -o ../data/esd_inspection.md
"""

import argparse
import sqlite3
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

BIG_FIVE_LEAGUES = (
    "England Premier League",
    "Spain LIGA BBVA",
    "Italy Serie A",
    "Germany 1. Bundesliga",
    "France Ligue 1",
)
DEMO_SEASON = "2015/2016"
XML_EVENT_COLUMNS = (
    "goal",
    "shoton",
    "shotoff",
    "foulcommit",
    "card",
    "cross",
    "corner",
    "possession",
)
LINEUP_COLUMNS = tuple(
    f"{side}_player_{number}" for side in ("home", "away") for number in range(1, 12)
)
SAMPLE_MAX_CHARS = 40


# --- small helpers -------------------------------------------------------------------


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def percent(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:.1f}%"


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return [*lines, ""]


def scalar(conn: sqlite3.Connection, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    return None if row is None else row[0]


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def column_info(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(row[1], row[2]) for row in conn.execute(f"PRAGMA table_info({quote(table)})")]


def has_columns(conn: sqlite3.Connection, table: str, *columns: str) -> bool:
    existing = {name for name, _ in column_info(conn, table)}
    return set(columns) <= existing


def connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


# --- report sections -----------------------------------------------------------------


def overview_section(conn: sqlite3.Connection) -> list[str]:
    rows = [
        (table, scalar(conn, f"SELECT COUNT(*) FROM {quote(table)}"), len(column_info(conn, table)))
        for table in table_names(conn)
    ]
    return ["## Tables", "", *markdown_table(["Table", "Rows", "Columns"], rows)]


def column_profile_section(conn: sqlite3.Connection, table: str) -> list[str]:
    columns = column_info(conn, table)
    null_sums = ", ".join(
        f"SUM(CASE WHEN {quote(name)} IS NULL THEN 1 ELSE 0 END)" for name, _ in columns
    )
    counts = conn.execute(f"SELECT COUNT(*), {null_sums} FROM {quote(table)}").fetchone()
    total, null_counts = counts[0], counts[1:]

    rows = []
    for (name, declared_type), nulls in zip(columns, null_counts, strict=True):
        sample = scalar(
            conn,
            f"SELECT {quote(name)} FROM {quote(table)} WHERE {quote(name)} IS NOT NULL LIMIT 1",
        )
        sample_text = "" if sample is None else str(sample)[:SAMPLE_MAX_CHARS]
        rows.append((name, declared_type or "(none)", percent(nulls or 0, total), sample_text))

    return [
        f"### `{table}` columns ({total} rows)",
        "",
        *markdown_table(["Column", "Declared type", "Null %", "Example value"], rows),
    ]


def match_section(conn: sqlite3.Connection) -> list[str]:
    tables = set(table_names(conn))
    if not {"Match", "League"} <= tables:
        return ["## Match checks", "", "Skipped: `Match` or `League` table missing.", ""]

    lines = ["## Match checks", ""]
    total = scalar(conn, "SELECT COUNT(*) FROM Match")
    first, last = conn.execute("SELECT MIN(date), MAX(date) FROM Match").fetchone()
    lines += [f"- Total matches: {total}", f"- Date range: {first} to {last}", ""]

    # Matches per league and season
    counts = conn.execute(
        "SELECT l.name, m.season, COUNT(*) FROM Match m "
        "JOIN League l ON l.id = m.league_id GROUP BY l.name, m.season"
    ).fetchall()
    seasons = sorted({season for _, season, _ in counts})
    by_league: dict[str, dict[str, int]] = {}
    for league, season, count in counts:
        by_league.setdefault(league, {})[season] = count
    lines += ["### Matches per league and season", ""]
    lines += markdown_table(
        ["League", *seasons, "Total"],
        [
            (league, *(per_season.get(s, 0) for s in seasons), sum(per_season.values()))
            for league, per_season in sorted(by_league.items())
        ],
    )

    lines += duplicate_and_integrity_lines(conn)
    lines += result_lines(conn)
    lines += odds_coverage_lines(conn)
    lines += lineup_and_event_coverage_lines(conn)
    lines += demo_season_lines(conn)
    return lines


def duplicate_and_integrity_lines(conn: sqlite3.Connection) -> list[str]:
    lines = ["### Duplicates and referential integrity", ""]

    if has_columns(conn, "Match", "match_api_id"):
        dupes = scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT match_api_id FROM Match "
            "GROUP BY match_api_id HAVING COUNT(*) > 1)",
        )
        lines.append(f"- Duplicate `match_api_id` values: {dupes}")
    if has_columns(conn, "Match", "league_id", "date", "home_team_api_id", "away_team_api_id"):
        dupes = scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT 1 FROM Match "
            "GROUP BY league_id, date, home_team_api_id, away_team_api_id HAVING COUNT(*) > 1)",
        )
        lines.append(f"- Duplicate (league, date, home team, away team) combinations: {dupes}")

    tables = set(table_names(conn))
    checks = [
        ("home_team_api_id", "Team", "team_api_id"),
        ("away_team_api_id", "Team", "team_api_id"),
        ("league_id", "League", "id"),
        ("country_id", "Country", "id"),
    ]
    for column, ref_table, ref_column in checks:
        if ref_table in tables and has_columns(conn, "Match", column):
            orphans = scalar(conn, orphan_count_sql("Match", column, ref_table, ref_column))
            lines.append(f"- `Match.{column}` not found in `{ref_table}`: {orphans}")

    if "Player" in tables:
        present = [c for c in LINEUP_COLUMNS if has_columns(conn, "Match", c)]
        orphans = sum(
            scalar(conn, orphan_count_sql("Match", column, "Player", "player_api_id"))
            for column in present
        )
        lines.append(
            f"- Lineup player ids not found in `Player` (across {len(present)} columns): {orphans}"
        )
    return [*lines, ""]


def orphan_count_sql(table: str, column: str, ref_table: str, ref_column: str) -> str:
    return (
        f"SELECT COUNT(*) FROM {quote(table)} t "
        f"LEFT JOIN {quote(ref_table)} r ON r.{quote(ref_column)} = t.{quote(column)} "
        f"WHERE t.{quote(column)} IS NOT NULL AND r.{quote(ref_column)} IS NULL"
    )


def result_lines(conn: sqlite3.Connection) -> list[str]:
    if not has_columns(conn, "Match", "season", "home_team_goal", "away_team_goal"):
        return []
    missing = scalar(
        conn, "SELECT COUNT(*) FROM Match WHERE home_team_goal IS NULL OR away_team_goal IS NULL"
    )
    rows = conn.execute(
        "SELECT season, COUNT(*), "
        "SUM(home_team_goal > away_team_goal), SUM(home_team_goal = away_team_goal), "
        "SUM(home_team_goal < away_team_goal), "
        "ROUND(AVG(home_team_goal), 2), ROUND(AVG(away_team_goal), 2) "
        "FROM Match GROUP BY season ORDER BY season"
    ).fetchall()
    table_rows = [
        (season, n, percent(h, n), percent(d, n), percent(a, n), avg_h, avg_a)
        for season, n, h, d, a, avg_h, avg_a in rows
    ]
    return [
        "### Results by season",
        "",
        f"- Matches with a missing score: {missing}",
        "",
        *markdown_table(
            [
                "Season",
                "Matches",
                "Home win",
                "Draw",
                "Away win",
                "Avg home goals",
                "Avg away goals",
            ],
            table_rows,
        ),
    ]


def bookmakers(conn: sqlite3.Connection) -> list[str]:
    """Bookmaker prefixes with a complete home/draw/away odds triple, e.g. B365H/B365D/B365A."""
    names = {name for name, _ in column_info(conn, "Match")}
    prefixes = {name[:-1] for name in names if name.endswith("H") and name[:-1].isupper()}
    return sorted(p for p in prefixes if {f"{p}H", f"{p}D", f"{p}A"} <= names)


def odds_coverage_lines(conn: sqlite3.Connection) -> list[str]:
    prefixes = bookmakers(conn)
    if not prefixes or not has_columns(conn, "Match", "season"):
        return ["### Bookmaker odds coverage", "", "No bookmaker odds columns found.", ""]

    complete = ", ".join(
        f"SUM({p}H IS NOT NULL AND {p}D IS NOT NULL AND {p}A IS NOT NULL)" for p in prefixes
    )
    rows = conn.execute(
        f"SELECT season, COUNT(*), {complete} FROM Match GROUP BY season ORDER BY season"
    ).fetchall()
    table_rows = [(season, *(percent(c, n) for c in coverage)) for season, n, *coverage in rows]
    return [
        "### Bookmaker odds coverage (share of matches with complete H/D/A odds)",
        "",
        *markdown_table(["Season", *prefixes], table_rows),
    ]


def lineup_and_event_coverage_lines(conn: sqlite3.Connection) -> list[str]:
    lineup = [c for c in LINEUP_COLUMNS if has_columns(conn, "Match", c)]
    events = [c for c in XML_EVENT_COLUMNS if has_columns(conn, "Match", c)]
    if not lineup and not events:
        return []

    parts = ["COUNT(*)"]
    if lineup:
        parts.append("SUM(" + " AND ".join(f"{quote(c)} IS NOT NULL" for c in lineup) + ")")
    parts += [f"SUM({quote(c)} IS NOT NULL AND {quote(c)} != '')" for c in events]
    rows = conn.execute(
        f"SELECT l.name, {', '.join(parts)} FROM Match m "
        "JOIN League l ON l.id = m.league_id GROUP BY l.name ORDER BY l.name"
    ).fetchall()

    headers = ["League", "Matches"]
    if lineup:
        headers.append(f"Full lineup ({len(lineup)} ids)")
    headers += [f"`{c}` XML" for c in events]
    table_rows = [
        (league, n, *(percent(value, n) for value in values)) for league, n, *values in rows
    ]
    return [
        "### Lineup and event-XML coverage by league",
        "",
        *markdown_table(headers, table_rows),
    ]


def demo_season_lines(conn: sqlite3.Connection) -> list[str]:
    if "Team" not in set(table_names(conn)):
        return []
    placeholders = ", ".join("?" for _ in BIG_FIVE_LEAGUES)
    rows = conn.execute(
        "SELECT l.name, COUNT(DISTINCT m.id), "
        "GROUP_CONCAT(DISTINCT t.team_long_name) FROM Match m "
        "JOIN League l ON l.id = m.league_id "
        "JOIN Team t ON t.team_api_id IN (m.home_team_api_id, m.away_team_api_id) "
        f"WHERE m.season = ? AND l.name IN ({placeholders}) "
        "GROUP BY l.name ORDER BY l.name",
        (DEMO_SEASON, *BIG_FIVE_LEAGUES),
    ).fetchall()
    lines = [
        f"### {DEMO_SEASON} Big Five leagues (overlap with StatsBomb open data)",
        "",
        f"- Total matches: {sum(row[1] for row in rows)}",
        "",
    ]
    for league, count, teams in rows:
        team_list = ", ".join(sorted((teams or "").split(",")))
        lines += [f"**{league}** ({count} matches): {team_list}", ""]
    return lines


def player_attributes_section(conn: sqlite3.Connection) -> list[str]:
    if "Player_Attributes" not in set(table_names(conn)):
        return []
    lines = ["## Player rating checks", ""]
    first, last = conn.execute("SELECT MIN(date), MAX(date) FROM Player_Attributes").fetchone()
    lines.append(f"- Rating snapshot date range: {first} to {last}")
    if has_columns(conn, "Player_Attributes", "player_api_id"):
        low, avg, high = conn.execute(
            "SELECT MIN(n), ROUND(AVG(n), 1), MAX(n) FROM "
            "(SELECT COUNT(*) AS n FROM Player_Attributes GROUP BY player_api_id)"
        ).fetchone()
        lines.append(f"- Snapshots per player: min {low}, avg {avg}, max {high}")
        if "Player" in set(table_names(conn)):
            orphans = scalar(
                conn,
                orphan_count_sql("Player_Attributes", "player_api_id", "Player", "player_api_id"),
            )
            lines.append(f"- `player_api_id` not found in `Player`: {orphans}")
    if has_columns(conn, "Player_Attributes", "overall_rating"):
        low, high = conn.execute(
            "SELECT MIN(overall_rating), MAX(overall_rating) FROM Player_Attributes"
        ).fetchone()
        lines.append(f"- `overall_rating` range: {low} to {high}")
    if has_columns(conn, "Player_Attributes", "player_api_id", "date"):
        dupes = scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT 1 FROM Player_Attributes "
            "GROUP BY player_api_id, date HAVING COUNT(*) > 1)",
        )
        lines.append(f"- Duplicate (player, date) snapshots: {dupes}")
    return [*lines, ""]


def team_section(conn: sqlite3.Connection) -> list[str]:
    tables = set(table_names(conn))
    if "Team" not in tables:
        return []
    lines = ["## Team checks", ""]
    if has_columns(conn, "Team", "team_api_id"):
        dupes = scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT team_api_id FROM Team "
            "GROUP BY team_api_id HAVING COUNT(*) > 1)",
        )
        lines.append(f"- Duplicate `team_api_id` values: {dupes}")
    if "Team_Attributes" in tables and has_columns(conn, "Team_Attributes", "date"):
        first, last = conn.execute("SELECT MIN(date), MAX(date) FROM Team_Attributes").fetchone()
        lines.append(f"- Team attribute snapshot date range: {first} to {last}")
    return [*lines, ""]


def build_report(conn: sqlite3.Connection) -> list[str]:
    lines = ["# European Soccer Database inspection", ""]
    lines += overview_section(conn)
    lines += match_section(conn)
    lines += player_attributes_section(conn)
    lines += team_section(conn)
    lines += ["## Column profiles", ""]
    for table in table_names(conn):
        lines += column_profile_section(conn, table)
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("database", type=Path, help="Path to the ESD database.sqlite file")
    parser.add_argument(
        "-o", "--output", type=Path, help="Write the report to this file (UTF-8) instead of stdout"
    )
    args = parser.parse_args(argv)

    try:
        conn = connect_read_only(args.database)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        report = "\n".join(build_report(conn)) + "\n"
    finally:
        conn.close()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

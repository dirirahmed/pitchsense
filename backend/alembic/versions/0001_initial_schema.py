"""Initial schema: countries, leagues, teams, players, ratings, matches, lineups.

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_leagues_country_id", "leagues", ["country_id"])

    op.create_table(
        "teams",
        sa.Column("team_api_id", sa.Integer(), nullable=False),
        sa.Column("long_name", sa.String(length=120), nullable=False),
        sa.Column("short_name", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("team_api_id"),
    )
    op.create_table(
        "players",
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("birthday", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("weight_lb", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("player_api_id"),
    )
    op.create_table(
        "player_ratings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("rating_date", sa.Date(), nullable=False),
        sa.Column("overall_rating", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["player_api_id"], ["players.player_api_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_api_id", "rating_date"),
    )
    op.create_index("ix_player_ratings_player_api_id", "player_ratings", ["player_api_id"])

    op.create_table(
        "matches",
        sa.Column("match_api_id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.String(length=9), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("home_team_api_id", sa.Integer(), nullable=False),
        sa.Column("away_team_api_id", sa.Integer(), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("b365_home", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("b365_draw", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("b365_away", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.ForeignKeyConstraint(["away_team_api_id"], ["teams.team_api_id"]),
        sa.ForeignKeyConstraint(["home_team_api_id"], ["teams.team_api_id"]),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.PrimaryKeyConstraint("match_api_id"),
    )
    op.create_index("ix_matches_league_id", "matches", ["league_id"])
    op.create_index("ix_matches_season", "matches", ["season"])
    op.create_index("ix_matches_match_date", "matches", ["match_date"])
    op.create_index("ix_matches_home_team_api_id", "matches", ["home_team_api_id"])
    op.create_index("ix_matches_away_team_api_id", "matches", ["away_team_api_id"])

    op.create_table(
        "match_lineups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_api_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_api_id"], ["matches.match_api_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["player_api_id"], ["players.player_api_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_api_id", "side", "slot"),
    )
    op.create_index("ix_match_lineups_match_api_id", "match_lineups", ["match_api_id"])
    op.create_index("ix_match_lineups_player_api_id", "match_lineups", ["player_api_id"])


def downgrade() -> None:
    op.drop_table("match_lineups")
    op.drop_table("matches")
    op.drop_table("player_ratings")
    op.drop_table("players")
    op.drop_table("teams")
    op.drop_table("leagues")
    op.drop_table("countries")

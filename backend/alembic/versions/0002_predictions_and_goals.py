"""Add predictions and match_goals tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("match_api_id", sa.Integer(), nullable=False),
        sa.Column("home_baseline_h", sa.Float(), nullable=False),
        sa.Column("home_baseline_d", sa.Float(), nullable=False),
        sa.Column("home_baseline_a", sa.Float(), nullable=False),
        sa.Column("odds_baseline_h", sa.Float(), nullable=True),
        sa.Column("odds_baseline_d", sa.Float(), nullable=True),
        sa.Column("odds_baseline_a", sa.Float(), nullable=True),
        sa.Column("lr_h", sa.Float(), nullable=False),
        sa.Column("lr_d", sa.Float(), nullable=False),
        sa.Column("lr_a", sa.Float(), nullable=False),
        sa.Column("gb_h", sa.Float(), nullable=False),
        sa.Column("gb_d", sa.Float(), nullable=False),
        sa.Column("gb_a", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_api_id"], ["matches.match_api_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("match_api_id"),
    )

    op.create_table(
        "match_goals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_api_id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("team_api_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_api_id"], ["matches.match_api_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["team_api_id"], ["teams.team_api_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_api_id", "minute", "team_api_id"),
    )
    op.create_index("ix_match_goals_match_api_id", "match_goals", ["match_api_id"])


def downgrade() -> None:
    op.drop_table("match_goals")
    op.drop_table("predictions")

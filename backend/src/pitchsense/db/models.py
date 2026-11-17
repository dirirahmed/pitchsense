"""SQLAlchemy ORM models for the match-prediction database.

The schema stays close to the shape of the European Soccer Database (hugomathien/soccer on
Kaggle) so the ETL can load it in one pass, while dropping columns the model doesn't use
(team FIFA attributes, the XML event columns, the lineup X/Y coordinates, every bookmaker
beyond Bet365).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base; Alembic uses `Base.metadata` to autogenerate."""


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Team(Base):
    __tablename__ = "teams"

    team_api_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    long_name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(10))


class Player(Base):
    __tablename__ = "players"

    player_api_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(120))
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The source labels these as height and weight, but height is in centimetres and
    # weight in pounds — we keep the units explicit in the column names.
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_lb: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PlayerRating(Base):
    """A FIFA "overall" rating snapshot for a player on a given date.

    The source has ~835 duplicate (player, date) rows; the ETL keeps the first one,
    and this unique constraint prevents more from appearing.
    """

    __tablename__ = "player_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_api_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_api_id"), index=True, nullable=False
    )
    rating_date: Mapped[date] = mapped_column(Date, nullable=False)
    overall_rating: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("player_api_id", "rating_date"),)


class Match(Base):
    """A finished league match with its final score and Bet365 odds."""

    __tablename__ = "matches"

    match_api_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    season: Mapped[str] = mapped_column(String(9), index=True)  # e.g. "2015/2016"
    match_date: Mapped[date] = mapped_column(Date, index=True)
    stage: Mapped[int] = mapped_column(Integer)
    home_team_api_id: Mapped[int] = mapped_column(ForeignKey("teams.team_api_id"), index=True)
    away_team_api_id: Mapped[int] = mapped_column(ForeignKey("teams.team_api_id"), index=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    # Bet365's home/draw/away decimal odds — the only bookmaker with consistent
    # ~87% coverage across every season (see data/esd_inspection.md).
    b365_home: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    b365_draw: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    b365_away: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)


class MatchLineup(Base):
    """One row per starting player, normalising the 22 lineup columns in the source.

    A match has at most 22 rows here (11 per side). Rows whose source cell is NULL
    are skipped during loading rather than stored as NULL player references.
    """

    __tablename__ = "match_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_api_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_api_id", ondelete="CASCADE"), index=True, nullable=False
    )
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "home" or "away"
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..11
    player_api_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_api_id"), index=True, nullable=False
    )

    __table_args__ = (UniqueConstraint("match_api_id", "side", "slot"),)

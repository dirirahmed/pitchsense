"""REST endpoints for browsing matches.

Supports the match-list page (GET /matches) and the single-match view
(GET /matches/{id}). Match detail embeds the two teams' names.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from pitchsense.db.models import Match, Team
from pitchsense.db.session import get_engine

router = APIRouter(prefix="/matches", tags=["matches"])

DEFAULT_SEASON = "2015/2016"


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


class TeamOut(BaseModel):
    team_api_id: int
    long_name: str
    short_name: str


class MatchSummary(BaseModel):
    match_api_id: int
    league_id: int
    season: str
    match_date: date
    stage: int
    home: TeamOut
    away: TeamOut
    home_goals: int
    away_goals: int


class MatchListResponse(BaseModel):
    season: str
    matches: list[MatchSummary]


def _team_lookup(session: Session, team_ids: set[int]) -> dict[int, TeamOut]:
    rows = session.execute(select(Team).where(Team.team_api_id.in_(team_ids))).scalars().all()
    return {
        team.team_api_id: TeamOut(
            team_api_id=team.team_api_id,
            long_name=team.long_name,
            short_name=team.short_name,
        )
        for team in rows
    }


@router.get("", response_model=MatchListResponse)
def list_matches(
    session: SessionDep,
    season: str = Query(DEFAULT_SEASON, description='Season key, e.g. "2015/2016"'),
    league_id: int | None = Query(None, description="Filter by league id"),
    limit: int = Query(100, ge=1, le=500),
) -> MatchListResponse:
    stmt = (
        select(Match).where(Match.season == season).order_by(Match.match_date, Match.match_api_id)
    )
    if league_id is not None:
        stmt = stmt.where(Match.league_id == league_id)
    stmt = stmt.limit(limit)

    matches = session.execute(stmt).scalars().all()
    team_ids = {m.home_team_api_id for m in matches} | {m.away_team_api_id for m in matches}
    teams = _team_lookup(session, team_ids)

    items = [
        MatchSummary(
            match_api_id=m.match_api_id,
            league_id=m.league_id,
            season=m.season,
            match_date=m.match_date,
            stage=m.stage,
            home=teams[m.home_team_api_id],
            away=teams[m.away_team_api_id],
            home_goals=m.home_goals,
            away_goals=m.away_goals,
        )
        for m in matches
    ]
    return MatchListResponse(season=season, matches=items)


@router.get("/{match_api_id}", response_model=MatchSummary)
def get_match(match_api_id: int, session: SessionDep) -> MatchSummary:
    match = session.get(Match, match_api_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    teams = _team_lookup(session, {match.home_team_api_id, match.away_team_api_id})
    return MatchSummary(
        match_api_id=match.match_api_id,
        league_id=match.league_id,
        season=match.season,
        match_date=match.match_date,
        stage=match.stage,
        home=teams[match.home_team_api_id],
        away=teams[match.away_team_api_id],
        home_goals=match.home_goals,
        away_goals=match.away_goals,
    )

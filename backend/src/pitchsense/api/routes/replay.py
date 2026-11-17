"""WebSocket replay: streams goal events and recomputed win probabilities.

Protocol
--------
The server opens with a `state` message describing the match and sends the opening
`probability` snapshot. For every goal the server emits a `goal` message followed
by a new `probability` snapshot — `clutch: true` when the swing crosses
`THRESHOLD_PP`. A final `final` message closes the replay.

Each probability snapshot carries the minute, the current score and the full
home/draw/away triple so the client can draw its line chart without extra state.

Replay speed is driven by a query parameter, in seconds per match-minute. Zero
plays back as fast as the client can read (useful for tests).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from pitchsense.db.models import Match, MatchGoal, Team
from pitchsense.db.session import get_engine
from pitchsense.live.clutch import detect_clutch
from pitchsense.live.engine import MatchState, WinProbabilities, simulate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["replay"])


def _serialise_probabilities(
    minute: int,
    home_score: int,
    away_score: int,
    probs: WinProbabilities,
    clutch: bool = False,
) -> dict[str, Any]:
    return {
        "type": "probability",
        "minute": minute,
        "home_score": home_score,
        "away_score": away_score,
        "home": probs.home,
        "draw": probs.draw,
        "away": probs.away,
        "clutch": clutch,
    }


async def _sleep_for_minutes(minutes: int, seconds_per_minute: float) -> None:
    if seconds_per_minute <= 0 or minutes <= 0:
        return
    await asyncio.sleep(minutes * seconds_per_minute)


def _load_replay(session: Session, match_api_id: int) -> tuple[Match, Team, Team, list[MatchGoal]]:
    match = session.get(Match, match_api_id)
    if match is None:
        raise LookupError("match not found")
    home = session.get(Team, match.home_team_api_id)
    away = session.get(Team, match.away_team_api_id)
    if home is None or away is None:
        raise LookupError("team not found")
    goals = list(
        session.execute(
            select(MatchGoal)
            .where(MatchGoal.match_api_id == match_api_id)
            .order_by(MatchGoal.minute, MatchGoal.id)
        )
        .scalars()
        .all()
    )
    return match, home, away, goals


async def _run_replay(
    websocket: WebSocket,
    match: Match,
    home: Team,
    away: Team,
    goals: list[MatchGoal],
    seconds_per_minute: float,
    rng: np.random.Generator,
) -> None:
    await websocket.send_json(
        {
            "type": "state",
            "match_api_id": match.match_api_id,
            "season": match.season,
            "home_team": {"team_api_id": home.team_api_id, "name": home.long_name},
            "away_team": {"team_api_id": away.team_api_id, "name": away.long_name},
            "final_home_goals": match.home_goals,
            "final_away_goals": match.away_goals,
            "n_goal_events": len(goals),
        }
    )

    minute = 0
    home_score = 0
    away_score = 0
    probs = simulate(MatchState(minute, home_score, away_score), rng=rng)
    await websocket.send_json(_serialise_probabilities(minute, home_score, away_score, probs))

    for goal in goals:
        await _sleep_for_minutes(goal.minute - minute, seconds_per_minute)
        minute = goal.minute
        if goal.team_api_id == match.home_team_api_id:
            home_score += 1
            scoring_side = "home"
        else:
            away_score += 1
            scoring_side = "away"

        await websocket.send_json(
            {
                "type": "goal",
                "minute": minute,
                "scoring_side": scoring_side,
                "home_score": home_score,
                "away_score": away_score,
            }
        )

        previous = probs
        probs = simulate(MatchState(minute, home_score, away_score), rng=rng)
        clutch = detect_clutch(previous, probs) is not None
        await websocket.send_json(
            _serialise_probabilities(minute, home_score, away_score, probs, clutch=clutch)
        )

    await _sleep_for_minutes(90 - minute, seconds_per_minute)
    await websocket.send_json(
        {
            "type": "final",
            "home_score": home_score,
            "away_score": away_score,
            "recorded_home_goals": match.home_goals,
            "recorded_away_goals": match.away_goals,
        }
    )


@router.websocket("/ws/matches/{match_api_id}/replay")
async def replay(
    websocket: WebSocket,
    match_api_id: int,
    seconds_per_minute: float = Query(0.5, ge=0.0, le=5.0),
) -> None:
    await websocket.accept()
    rng = np.random.default_rng()

    try:
        with Session(get_engine()) as session:
            try:
                match, home, away, goals = _load_replay(session, match_api_id)
            except LookupError as error:
                await websocket.send_json({"type": "error", "message": str(error)})
                await websocket.close(code=1008)
                return

        await _run_replay(websocket, match, home, away, goals, seconds_per_minute, rng)
    except WebSocketDisconnect:
        logger.info("Replay disconnected by client for match %d", match_api_id)
        return

    if websocket.client_state is not WebSocketState.DISCONNECTED:
        await websocket.close()

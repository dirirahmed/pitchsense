"""Feature engineering for pre-match prediction.

Every feature is computed from matches that strictly predate the target match's
`match_date`, so no information leaks from the future into the training set.

The entry point `build_training_table` returns one row per match with the model's
inputs (form, head-to-head, starting XI rating) and the label (outcome).
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Final

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class Outcome(IntEnum):
    """Three-way match outcome; values match sklearn's convention of 0-indexed classes."""

    HOME_WIN = 0
    DRAW = 1
    AWAY_WIN = 2


FORM_WINDOW: Final = 5
H2H_WINDOW: Final = 5

FEATURE_COLUMNS: Final[list[str]] = [
    "home_ppg_last5",
    "away_ppg_last5",
    "home_gs_avg_last5",
    "home_gc_avg_last5",
    "away_gs_avg_last5",
    "away_gc_avg_last5",
    "h2h_home_win_rate",
    "h2h_draw_rate",
    "h2h_away_win_rate",
    "home_avg_rating",
    "away_avg_rating",
]

CONTEXT_COLUMNS: Final[list[str]] = [
    "match_api_id",
    "league_id",
    "season",
    "match_date",
    "home_team_api_id",
    "away_team_api_id",
    "home_goals",
    "away_goals",
    "b365_home",
    "b365_draw",
    "b365_away",
]


def compute_outcome(home_goals: pd.Series, away_goals: pd.Series) -> pd.Series:
    """Vectorised three-way outcome label from the final score."""
    conditions = [home_goals > away_goals, home_goals < away_goals]
    choices = [int(Outcome.HOME_WIN), int(Outcome.AWAY_WIN)]
    return pd.Series(
        np.select(conditions, choices, default=int(Outcome.DRAW)), index=home_goals.index
    )


def load_matches(session: Session) -> pd.DataFrame:
    """Read the matches table into a DataFrame sorted chronologically."""
    sql = text(
        """
        SELECT match_api_id, league_id, season, match_date,
               home_team_api_id, away_team_api_id,
               home_goals, away_goals,
               b365_home, b365_draw, b365_away
        FROM matches
        ORDER BY match_date, match_api_id
        """
    )
    df = pd.read_sql(sql, session.connection())
    df["match_date"] = pd.to_datetime(df["match_date"])
    df["outcome"] = compute_outcome(df["home_goals"], df["away_goals"])
    return df


def compute_form_features(matches: pd.DataFrame) -> pd.DataFrame:
    """For each match, points/goals-per-game over the team's previous `FORM_WINDOW` matches.

    Uses `shift(1)` before the rolling window so the current match never influences its
    own feature values.
    """

    def perspective(side: str) -> pd.DataFrame:
        team_col = f"{side}_team_api_id"
        own_goals = f"{side}_goals"
        opp_goals = "away_goals" if side == "home" else "home_goals"
        win_class = int(Outcome.HOME_WIN if side == "home" else Outcome.AWAY_WIN)

        df = matches[
            ["match_api_id", "match_date", team_col, own_goals, opp_goals, "outcome"]
        ].rename(columns={team_col: "team_api_id", own_goals: "gs", opp_goals: "gc"})
        df["points"] = np.select(
            [df["outcome"] == win_class, df["outcome"] == int(Outcome.DRAW)], [3, 1], default=0
        )
        return df[["match_api_id", "match_date", "team_api_id", "points", "gs", "gc"]]

    rows = pd.concat([perspective("home"), perspective("away")], ignore_index=True)
    rows = rows.sort_values(["team_api_id", "match_date", "match_api_id"]).reset_index(drop=True)

    def rolling_mean(series: pd.Series) -> pd.Series:
        return series.shift(1).rolling(FORM_WINDOW, min_periods=1).mean()

    grouped = rows.groupby("team_api_id", sort=False)
    rows["ppg_last5"] = grouped["points"].transform(rolling_mean)
    rows["gs_avg_last5"] = grouped["gs"].transform(rolling_mean)
    rows["gc_avg_last5"] = grouped["gc"].transform(rolling_mean)

    # Join back to each match for home and away separately.
    home = (
        matches[["match_api_id", "home_team_api_id"]]
        .merge(
            rows[["match_api_id", "team_api_id", "ppg_last5", "gs_avg_last5", "gc_avg_last5"]],
            left_on=["match_api_id", "home_team_api_id"],
            right_on=["match_api_id", "team_api_id"],
            how="left",
        )
        .rename(
            columns={
                "ppg_last5": "home_ppg_last5",
                "gs_avg_last5": "home_gs_avg_last5",
                "gc_avg_last5": "home_gc_avg_last5",
            }
        )[["match_api_id", "home_ppg_last5", "home_gs_avg_last5", "home_gc_avg_last5"]]
    )

    away = (
        matches[["match_api_id", "away_team_api_id"]]
        .merge(
            rows[["match_api_id", "team_api_id", "ppg_last5", "gs_avg_last5", "gc_avg_last5"]],
            left_on=["match_api_id", "away_team_api_id"],
            right_on=["match_api_id", "team_api_id"],
            how="left",
        )
        .rename(
            columns={
                "ppg_last5": "away_ppg_last5",
                "gs_avg_last5": "away_gs_avg_last5",
                "gc_avg_last5": "away_gc_avg_last5",
            }
        )[["match_api_id", "away_ppg_last5", "away_gs_avg_last5", "away_gc_avg_last5"]]
    )

    return home.merge(away, on="match_api_id")


def compute_h2h_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Head-to-head rates over the home team's previous meetings with the away team."""

    def perspective(side: str) -> pd.DataFrame:
        team_col = f"{side}_team_api_id"
        opp_col = "away_team_api_id" if side == "home" else "home_team_api_id"
        win_class = int(Outcome.HOME_WIN if side == "home" else Outcome.AWAY_WIN)
        loss_class = int(Outcome.AWAY_WIN if side == "home" else Outcome.HOME_WIN)

        df = matches[["match_api_id", "match_date", team_col, opp_col, "outcome"]].rename(
            columns={team_col: "team", opp_col: "opponent"}
        )
        df["is_win"] = (df["outcome"] == win_class).astype(int)
        df["is_draw"] = (df["outcome"] == int(Outcome.DRAW)).astype(int)
        df["is_loss"] = (df["outcome"] == loss_class).astype(int)
        return df[
            ["match_api_id", "match_date", "team", "opponent", "is_win", "is_draw", "is_loss"]
        ]

    rows = pd.concat([perspective("home"), perspective("away")], ignore_index=True)
    rows = rows.sort_values(["team", "opponent", "match_date", "match_api_id"]).reset_index(
        drop=True
    )

    def rolling_sum(series: pd.Series) -> pd.Series:
        return series.shift(1).rolling(H2H_WINDOW, min_periods=1).sum()

    grouped = rows.groupby(["team", "opponent"], sort=False)
    rows["wins"] = grouped["is_win"].transform(rolling_sum)
    rows["draws"] = grouped["is_draw"].transform(rolling_sum)
    rows["losses"] = grouped["is_loss"].transform(rolling_sum)
    rows["meetings"] = rows[["wins", "draws", "losses"]].sum(axis=1)

    # Take the home-team perspective to describe each match.
    home_view = matches[["match_api_id", "home_team_api_id"]].merge(
        rows[["match_api_id", "team", "wins", "draws", "losses", "meetings"]],
        left_on=["match_api_id", "home_team_api_id"],
        right_on=["match_api_id", "team"],
        how="left",
    )

    meetings = home_view["meetings"]
    safe = meetings.where(meetings > 0, np.nan)
    home_view["h2h_home_win_rate"] = home_view["wins"] / safe
    home_view["h2h_draw_rate"] = home_view["draws"] / safe
    home_view["h2h_away_win_rate"] = home_view["losses"] / safe

    return home_view[["match_api_id", "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate"]]


def compute_rating_features(session: Session, matches: pd.DataFrame) -> pd.DataFrame:
    """For each match side, the average FIFA 'overall' rating of its starting XI.

    Each player's rating is the snapshot whose `rating_date` is the latest one that is
    not after `match_date`; players with no earlier snapshot contribute nothing.
    """
    lineups = pd.read_sql(
        text(
            """
            SELECT ml.match_api_id, ml.side, ml.player_api_id, m.match_date
            FROM match_lineups ml
            JOIN matches m ON m.match_api_id = ml.match_api_id
            """
        ),
        session.connection(),
    )
    if lineups.empty:
        return matches[["match_api_id"]].assign(home_avg_rating=np.nan, away_avg_rating=np.nan)

    lineups["match_date"] = pd.to_datetime(lineups["match_date"])
    ratings = pd.read_sql(
        text("SELECT player_api_id, rating_date, overall_rating FROM player_ratings"),
        session.connection(),
    )
    ratings["rating_date"] = pd.to_datetime(ratings["rating_date"])

    lineups_sorted = lineups.sort_values(["match_date", "player_api_id"])
    ratings_sorted = ratings.sort_values(["rating_date", "player_api_id"])
    enriched = pd.merge_asof(
        lineups_sorted,
        ratings_sorted,
        left_on="match_date",
        right_on="rating_date",
        by="player_api_id",
        direction="backward",
    )

    agg = enriched.groupby(["match_api_id", "side"])["overall_rating"].mean().reset_index()
    pivot = agg.pivot(index="match_api_id", columns="side", values="overall_rating").reset_index()
    pivot.columns.name = None
    return pivot.rename(columns={"home": "home_avg_rating", "away": "away_avg_rating"})


def build_training_table(session: Session) -> pd.DataFrame:
    """Return matches with every model feature and label attached, dropping rows with NaNs.

    The caller splits by season to form train/validation/test sets.
    """
    matches = load_matches(session)
    logger.info("Loaded %d matches", len(matches))

    form = compute_form_features(matches)
    h2h = compute_h2h_features(matches)
    ratings = compute_rating_features(session, matches)

    table = (
        matches.merge(form, on="match_api_id", how="left")
        .merge(h2h, on="match_api_id", how="left")
        .merge(ratings, on="match_api_id", how="left")
    )

    columns = CONTEXT_COLUMNS + FEATURE_COLUMNS + ["outcome"]
    ensured = [column for column in columns if column != "match_api_id"]
    table = table[["match_api_id", *ensured]]

    complete = table.dropna(subset=FEATURE_COLUMNS)
    logger.info(
        "Kept %d/%d matches after dropping rows with missing features", len(complete), len(table)
    )
    return complete.reset_index(drop=True)

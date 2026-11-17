"""Serve the pre-match predictions produced by the training pipeline."""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pitchsense.db.models import Prediction
from pitchsense.db.session import get_engine


def _is_present(value: float | None) -> bool:
    """Treat None and NaN alike as 'no odds for this match'."""
    return value is not None and not math.isnan(value)


router = APIRouter(prefix="/matches", tags=["predictions"])


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


class ProbabilityTriple(BaseModel):
    home: float = Field(..., ge=0.0, le=1.0)
    draw: float = Field(..., ge=0.0, le=1.0)
    away: float = Field(..., ge=0.0, le=1.0)


class PredictionResponse(BaseModel):
    match_api_id: int
    always_home_baseline: ProbabilityTriple
    bet365_odds_baseline: ProbabilityTriple | None
    logistic_regression: ProbabilityTriple
    gradient_boosting: ProbabilityTriple


@router.get("/{match_api_id}/prediction", response_model=PredictionResponse)
def get_prediction(match_api_id: int, session: SessionDep) -> PredictionResponse:
    prediction = session.get(Prediction, match_api_id)
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prediction available for this match",
        )

    odds_baseline: ProbabilityTriple | None = None
    home_odds = prediction.odds_baseline_h
    if _is_present(home_odds):
        # odds_baseline_d/a are guaranteed non-null when _h is non-null (ETL invariant).
        assert home_odds is not None  # narrows for mypy
        odds_baseline = ProbabilityTriple(
            home=home_odds,
            draw=prediction.odds_baseline_d or 0.0,
            away=prediction.odds_baseline_a or 0.0,
        )

    return PredictionResponse(
        match_api_id=prediction.match_api_id,
        always_home_baseline=ProbabilityTriple(
            home=prediction.home_baseline_h,
            draw=prediction.home_baseline_d,
            away=prediction.home_baseline_a,
        ),
        bet365_odds_baseline=odds_baseline,
        logistic_regression=ProbabilityTriple(
            home=prediction.lr_h, draw=prediction.lr_d, away=prediction.lr_a
        ),
        gradient_boosting=ProbabilityTriple(
            home=prediction.gb_h, draw=prediction.gb_d, away=prediction.gb_a
        ),
    )

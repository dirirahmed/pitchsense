"""Load the predictions CSV written by `pitchsense.ml.train` into PostgreSQL.

Idempotent: a second run overwrites existing predictions for the same match. We use
an UPSERT because the CSV is the source of truth and rerunning training must be
reflected in the API's answers.

Usage (from backend/):
    uv run python -m pitchsense.etl.load_predictions ../data/artifacts/predictions.csv
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pandas as pd
from sqlalchemy import Engine, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pitchsense.db.models import Prediction
from pitchsense.db.session import get_engine

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "match_api_id",
    "home_baseline_h",
    "home_baseline_d",
    "home_baseline_a",
    "odds_baseline_h",
    "odds_baseline_d",
    "odds_baseline_a",
    "lr_h",
    "lr_d",
    "lr_a",
    "gb_h",
    "gb_d",
    "gb_a",
)


def load_predictions(csv_path: Path, engine: Engine | None = None) -> int:
    """Upsert every row from `csv_path` into the `predictions` table."""
    if engine is None:
        engine = get_engine()

    df = pd.read_csv(csv_path)
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"predictions CSV is missing columns: {missing}")

    raw_records = df[list(REQUIRED_COLUMNS)].to_dict(orient="records")
    # pandas represents missing floats as NaN; Postgres needs real NULLs so the API's
    # `odds_baseline_h is not None` check works later.
    records: list[dict[str, object]] = [
        {str(k): (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        for row in raw_records
    ]
    if not records:
        return 0

    table = cast(Table, Prediction.__table__)
    with engine.begin() as connection:
        statement = pg_insert(table).values(records)
        update_columns = {column: statement.excluded[column] for column in REQUIRED_COLUMNS[1:]}
        statement = statement.on_conflict_do_update(
            index_elements=["match_api_id"],
            set_=update_columns,
        )
        connection.execute(statement)
    return len(records)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("csv", type=Path, help="Path to predictions.csv")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.csv.is_file():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    n = load_predictions(args.csv)
    print(f"predictions_upserted={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Model factories for pre-match prediction.

Both estimators output calibrated class probabilities (``predict_proba``) with three
columns in the order home-win, draw, away-win — the class order sklearn uses when it
learns from integer labels 0, 1, 2.
"""

from __future__ import annotations

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def make_logistic_regression(random_state: int = 42) -> Pipeline:
    """Linear baseline: median-imputed features, standardised, multinomial logistic.

    Features with wildly different scales (`ppg_last5` is in [0, 3], `home_avg_rating`
    is in [40, 95]) must be standardised before logistic regression — otherwise
    regularisation effectively penalises the small-scale features out of existence.
    """
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=2000,
                    C=1.0,
                    random_state=random_state,
                ),
            ),
        ]
    )


def make_gradient_boosting(random_state: int = 42) -> Pipeline:
    """Non-linear model: median-imputed features into a shallow boosting ensemble.

    Scaling has no effect on trees, so it's left out. 200 shallow trees is a sensible
    starting point; further tuning belongs in a follow-up change.
    """
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                GradientBoostingClassifier(
                    n_estimators=200,
                    max_depth=3,
                    learning_rate=0.05,
                    random_state=random_state,
                ),
            ),
        ]
    )

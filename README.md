# PitchSense

Soccer match prediction and analysis: pre-match win/draw/loss probabilities, historical match replays with live-updating probabilities, clutch-moment detection, and player movement analysis.

> **Status:** Phase 1 (repository and infrastructure). The demo, architecture diagram and live link will be added as features land.

## Technology stack

| Area | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy |
| Live communication | WebSockets |
| ML | scikit-learn (Logistic Regression baseline, Gradient Boosting) |
| Database | PostgreSQL |
| Frontend | React, TypeScript, Vite |
| Testing | pytest, Vitest |
| Infrastructure | Docker, Docker Compose, GitHub Actions |

## Data sources

- **European Soccer Database** (Kaggle): historical matches, teams and player ratings, 2008–2016. Player ratings come from the FIFA video games, not measured performance.
- **StatsBomb Open Data**: event-level data for the 2015/16 Big 5 leagues season, used for match replays and player analysis.

Coverage and limitations will be documented after the data has been inspected (Phase 2).

## Local setup

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 22+.

```bash
cp .env.example .env          # then edit values
docker compose up --build     # db on :5432, API on :8000, frontend on :5173
```

Check the API at http://localhost:8000/health and the interactive docs at http://localhost:8000/docs.

### Backend without Docker

```bash
cd backend
uv sync
uv run pytest -m "not integration"   # unit tests, no database needed
uv run pytest                        # all tests, needs PostgreSQL from .env
uv run ruff check . && uv run mypy
```

### Frontend without Docker

```bash
cd frontend
npm install
npm run dev
npm test
```

## Deployment

Production runs on free tiers, defined in [`render.yaml`](render.yaml):

- **API:** Render web service built from `backend/Dockerfile`. Free instances sleep after 15 minutes without traffic and take about a minute to wake.
- **Frontend:** Render static site built from `frontend/`.
- **Database:** Neon serverless PostgreSQL.

Render deploys each service only after the GitHub Actions checks on `main` pass. Secrets (`DATABASE_URL`) live in the Render dashboard, never in the repository.

## Results

Only verified measurements are recorded here. Anything not yet measured is labelled as such.

| Metric | Measurement | Result |
|---|---|---|
| Historical dataset | Number of matches and leagues | Not measured yet |
| Pre-match model | Accuracy and log loss (test set) | Not measured yet |
| Home-team baseline | Accuracy and log loss (test set) | Not measured yet |
| Bookmaker odds reference | Accuracy and log loss (test set) | Not measured yet |
| Next-action model | Accuracy (test set) | Not measured yet |
| Next-action baselines | Accuracy (test set) | Not measured yet |
| Simulation engine | Simulations per prediction | Not measured yet |
| Simulation performance | Average recalculation time (ms) | Not measured yet |
| WebSockets | Event-to-client update latency (ms) | Not measured yet |
| Backend testing | pytest test count and coverage | Not measured yet |
| Frontend testing | Vitest test count and coverage | Not measured yet |
| Deployment | Public URL | Not deployed yet |
| Usage | Visits/users | Not measured yet |

## Known limitations

To be documented as each phase is completed.

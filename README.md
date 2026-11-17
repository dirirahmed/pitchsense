# PitchSense

**Live demo:** https://pitchsense-0ydl.onrender.com

Soccer match prediction and live replay. Pick a real 2015/16 match, see what the models thought would happen, press Play, and watch the win probability move with every goal.

Built because I wanted to see how far a straightforward ML pipeline could get against the bookmakers.

## What it does

- **Pre-match predictions** from two models (Logistic Regression and Gradient Boosting) and two baselines (always-pick-home and Bet365 odds)
- **Live replay** of every goal from the real match, streamed over WebSocket
- **Monte Carlo win probability** recomputed after each goal (10,000 simulations per call, Poisson goal rates adjusted for score and red cards)
- **Clutch moment detection** when a goal swings the probability by more than 15 percentage points

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic, WebSockets |
| ML | scikit-learn (Logistic Regression, Gradient Boosting), NumPy, Pandas |
| Database | PostgreSQL (Neon serverless in production) |
| Frontend | React, TypeScript, Vite, React Router, Recharts |
| Tests | pytest + httpx (backend), Vitest + Testing Library (frontend) |
| Infra | Docker, Docker Compose, GitHub Actions, Render |

## Architecture

```
┌──────────────┐   HTTPS/WSS    ┌──────────────┐    SQL     ┌──────────────┐
│  React SPA   │ ─────────────> │  FastAPI     │ ────────>  │  PostgreSQL  │
│  (Render     │ <───────────── │  (Render     │ <────────  │  (Neon)      │
│   Static)    │                │   Docker)    │            │              │
└──────────────┘                └──────────────┘            └──────────────┘
                                      │
                                      ├─ Pre-match REST
                                      ├─ WebSocket replay
                                      └─ Monte Carlo engine
```

Offline training writes models and precomputed predictions to `data/artifacts/`. An ETL pipeline ingests the Kaggle European Soccer Database into Postgres.

## Results

All numbers measured on the 2015/16 season held out from training (no overlap with the training set). Training data: 2008/09–2014/15.

| Model | Accuracy | Log loss | n |
|---|---|---|---|
| Always pick home (floor) | 44.2% | 19.29 | 3,089 |
| Logistic Regression | **50.2%** | 0.998 | 3,089 |
| Gradient Boosting | **50.3%** | 1.003 | 3,089 |
| Bet365 odds (ceiling) | 52.3% | 0.975 | 2,693 |

The models beat the trivial baseline by 6 percentage points and come within 2 of the bookmakers. The log loss gap between Gradient Boosting (1.003) and Bet365 (0.975) is where the remaining room sits.

### Feature set

- Last-5-match points per game (per team)
- Last-5-match goals scored and conceded (per team)
- Head-to-head record over the last 5 meetings
- Average FIFA "overall" rating for the starting XI (snapshot nearest the match date)

### Dataset

| Thing | Count |
|---|---|
| Matches | 25,979 |
| Teams | 299 |
| Players | 11,060 |
| FIFA rating snapshots | 183,142 |
| Starting XI lineups | 542,281 player slots |
| Goal events | 39,798 (across 13,222 matches with full XML) |

### Testing and coverage

| Suite | Count | Coverage |
|---|---|---|
| Backend (pytest) | 62 | 75% |
| Frontend (Vitest) | 7 | not measured |

## Known limitations

- **FIFA ratings are video-game ratings**, not measured performance. They're useful as a proxy for squad strength, nothing more.
- **~210 matches in the test season** have no prediction because at least one starting player had no FIFA rating snapshot before the match date. These are mostly opening-weekend matches with new signings.
- **Goal event XML is incomplete in some leagues.** Premier League, Bundesliga, Serie A and La Liga have ~100% coverage in 2015/16; Ligue 1 has 66%, other leagues have very little. Matches without events still show predictions but have an empty replay.
- **No tactical adjustments** for substitutions — they trigger a recalculation but don't modify the goal rates. Inventing tactical effects wasn't worth faking.
- **Monte Carlo could be exact.** With independent Poisson goals the probabilities can be computed analytically. The simulation is kept because it extends cleanly to red cards and time-varying rates; the closed form is used as a test oracle.
- **The free hosting spins down after 15 minutes** of no traffic. First load after a quiet period takes about 60 seconds for the backend to wake up.

## Local setup

Requires Docker, [uv](https://docs.astral.sh/uv/), and Node 22+.

```bash
cp .env.example .env            # defaults are fine for local dev
docker compose up --build       # Postgres + backend + Vite
```

The frontend serves at http://localhost:5173 and the API at http://localhost:8000. Interactive API docs are at http://localhost:8000/docs.

To train a model yourself, download the [Kaggle European Soccer Database](https://www.kaggle.com/datasets/hugomathien/soccer) into `data/raw/database.sqlite` and run, from `backend/`:

```bash
uv run alembic upgrade head
uv run python -m pitchsense.etl.load_esd ../data/raw/database.sqlite -v
uv run python -m pitchsense.etl.load_goals ../data/raw/database.sqlite -v
uv run python -m pitchsense.ml.train --out ../data/artifacts -v
uv run python -m pitchsense.etl.load_predictions ../data/artifacts/predictions.csv -v
```

## Development

- `uv run pytest --cov` runs the backend test suite against a running Postgres
- `uv run ruff check . && uv run mypy` lints and type-checks the backend
- `npm test` runs frontend tests; `npm run lint && npm run typecheck` checks the rest

CI runs the whole thing on every push to `main`. Render redeploys only after CI passes.

## Credits

- Historical match data: [European Soccer Database by Hugo Mathien (Kaggle)](https://www.kaggle.com/datasets/hugomathien/soccer)
- Big Five leagues 2015/16 overlap inspired by StatsBomb's open data release

---

Built by Dirir Ibrahim. [GitHub](https://github.com/dirirahmed/pitchsense).

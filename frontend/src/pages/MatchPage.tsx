import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  getMatch,
  getPrediction,
  type MatchSummary,
  type PredictionResponse,
} from '../api/matches';
import { GoalEventList } from '../components/GoalEventList';
import { PredictionCard } from '../components/PredictionCard';
import { ProbabilityChart } from '../components/ProbabilityChart';
import { useReplay } from '../hooks/useReplay';

interface LoadedData {
  match: MatchSummary;
  prediction: PredictionResponse | null;
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: LoadedData }
  | { kind: 'error'; message: string };

export function MatchPage() {
  const params = useParams<{ id: string }>();
  const matchId = params.id ? Number(params.id) : null;
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  useEffect(() => {
    if (matchId === null || Number.isNaN(matchId)) {
      setState({ kind: 'error', message: 'Invalid match id' });
      return;
    }
    const controller = new AbortController();

    const matchPromise = getMatch(matchId, controller.signal);
    const predictionPromise = getPrediction(matchId, controller.signal).catch(() => null);

    Promise.all([matchPromise, predictionPromise])
      .then(([match, prediction]) => {
        setState({ kind: 'ready', data: { match, prediction } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : 'Could not load match';
        setState({ kind: 'error', message });
      });

    return () => controller.abort();
  }, [matchId]);

  return (
    <main className="match-page">
      <Link to="/" className="back-link">← Back to matches</Link>

      {state.kind === 'loading' ? <p className="placeholder">Loading match…</p> : null}
      {state.kind === 'error' ? (
        <p className="placeholder placeholder--error">{state.message}</p>
      ) : null}
      {state.kind === 'ready' ? (
        <MatchContent match={state.data.match} prediction={state.data.prediction} />
      ) : null}
    </main>
  );
}

function MatchContent({ match, prediction }: LoadedData) {
  const replay = useReplay({ matchId: match.match_api_id, secondsPerMinute: 0.3 });

  return (
    <>
      <header className="match-header">
        <p className="match-header__meta">
          {match.match_date} · Season {match.season} · Stage {match.stage}
        </p>
        <div className="match-header__teams">
          <span className="match-header__team">{match.home.long_name}</span>
          <span className="match-header__score">
            {match.home_goals} – {match.away_goals}
          </span>
          <span className="match-header__team">{match.away.long_name}</span>
        </div>
      </header>

      <section className="section">
        <h2>Pre-match predictions</h2>
        <div className="prediction-grid">
          <PredictionCard
            title="Always home (baseline)"
            description="Trivial baseline: always pick the home team to win."
            probabilities={prediction?.always_home_baseline ?? null}
          />
          <PredictionCard
            title="Logistic Regression"
            description="Linear model on team form, head-to-head and average FIFA rating."
            probabilities={prediction?.logistic_regression ?? null}
          />
          <PredictionCard
            title="Gradient Boosting"
            description="Non-linear model on the same features."
            probabilities={prediction?.gradient_boosting ?? null}
            highlight
          />
          <PredictionCard
            title="Bet365 odds"
            description="Bookmaker's implied probabilities with overround removed."
            probabilities={prediction?.bet365_odds_baseline ?? null}
          />
        </div>
      </section>

      <section className="section">
        <div className="section__header">
          <h2>Live replay</h2>
          <ReplayControls status={replay.status} onStart={replay.start} onStop={replay.stop} />
        </div>
        {replay.status === 'error' ? (
          <p className="placeholder placeholder--error">{replay.error}</p>
        ) : null}
        {replay.probabilities.length > 0 ? (
          <>
            <ProbabilityChart probabilities={replay.probabilities} />
            <div className="replay-detail">
              <h3>Goals</h3>
              <GoalEventList
                goals={replay.goals}
                probabilities={replay.probabilities}
                homeTeam={match.home.long_name}
                awayTeam={match.away.long_name}
              />
            </div>
          </>
        ) : (
          <p className="placeholder">
            Press Play to replay the match. The Monte Carlo engine recomputes the win
            probability after every goal.
          </p>
        )}
      </section>
    </>
  );
}

interface ReplayControlsProps {
  status: ReturnType<typeof useReplay>['status'];
  onStart: () => void;
  onStop: () => void;
}

function ReplayControls({ status, onStart, onStop }: ReplayControlsProps) {
  if (status === 'idle' || status === 'finished' || status === 'error') {
    return (
      <button type="button" className="button button--primary" onClick={onStart}>
        {status === 'finished' ? 'Replay again' : 'Play'}
      </button>
    );
  }
  return (
    <div className="replay-controls">
      <span className="replay-controls__status">
        {status === 'connecting' ? 'Connecting…' : 'Live'}
      </span>
      <button type="button" className="button" onClick={onStop}>
        Stop
      </button>
    </div>
  );
}

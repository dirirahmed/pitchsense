import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { listMatches, type MatchListResponse, type MatchSummary } from '../api/matches';

const DEFAULT_SEASON = '2015/2016';

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: MatchListResponse }
  | { kind: 'error'; message: string };

export function MatchListPage() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    listMatches(DEFAULT_SEASON, { limit: 50, signal: controller.signal })
      .then((data) => setState({ kind: 'ready', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : 'Could not load matches';
        setState({ kind: 'error', message });
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="match-list-page">
      <header className="page-header">
        <h1>PitchSense</h1>
        <p className="page-subtitle">
          Replay a real {DEFAULT_SEASON} match. Watch the win probability move with every goal.
        </p>
      </header>

      {state.kind === 'loading' ? (
        <p className="placeholder">Waking up the API… first load can take a minute.</p>
      ) : null}

      {state.kind === 'error' ? (
        <p className="placeholder placeholder--error">
          Could not load matches: {state.message}
        </p>
      ) : null}

      {state.kind === 'ready' ? <MatchGrid matches={state.data.matches} /> : null}
    </main>
  );
}

function MatchGrid({ matches }: { matches: MatchSummary[] }) {
  if (matches.length === 0) {
    return <p className="placeholder">No matches found for this season.</p>;
  }
  return (
    <ul className="match-grid">
      {matches.map((match) => (
        <li key={match.match_api_id}>
          <Link to={`/match/${match.match_api_id}`} className="match-card">
            <time className="match-card__date">{match.match_date}</time>
            <div className="match-card__teams">
              <span>{match.home.long_name}</span>
              <span className="match-card__score">
                {match.home_goals} – {match.away_goals}
              </span>
              <span>{match.away.long_name}</span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

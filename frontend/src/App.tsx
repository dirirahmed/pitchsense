import { useEffect, useState } from 'react';

import { fetchHealth, type HealthStatus } from './api/health';
import './App.css';

type ApiState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthStatus }
  | { kind: 'error'; message: string };

function describe(state: ApiState): string {
  switch (state.kind) {
    case 'loading':
      return 'Connecting to the API…';
    case 'ready':
      return state.health.status === 'ok'
        ? 'API connected'
        : 'API reachable, database unavailable';
    case 'error':
      return `API unreachable: ${state.message}`;
  }
}

export default function App() {
  const [state, setState] = useState<ApiState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : 'Unknown error';
        setState({ kind: 'error', message });
      });
    return () => controller.abort();
  }, []);

  const tone =
    state.kind === 'loading'
      ? 'pending'
      : state.kind === 'ready' && state.health.status === 'ok'
        ? 'ok'
        : 'problem';

  return (
    <main className="app">
      <h1>PitchSense</h1>
      <p className="tagline">Soccer match predictions, live replays and player analysis.</p>
      <p className={`api-status api-status--${tone}`} role="status">
        {describe(state)}
      </p>
    </main>
  );
}

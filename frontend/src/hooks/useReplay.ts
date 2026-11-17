import { useEffect, useRef, useState } from 'react';

import { WS_URL } from '../config';

/** Messages emitted by the server over the replay WebSocket. */
export interface StateMessage {
  type: 'state';
  match_api_id: number;
  season: string;
  home_team: { team_api_id: number; name: string };
  away_team: { team_api_id: number; name: string };
  final_home_goals: number;
  final_away_goals: number;
  n_goal_events: number;
}

export interface ProbabilityMessage {
  type: 'probability';
  minute: number;
  home_score: number;
  away_score: number;
  home: number;
  draw: number;
  away: number;
  clutch: boolean;
}

export interface GoalMessage {
  type: 'goal';
  minute: number;
  scoring_side: 'home' | 'away';
  home_score: number;
  away_score: number;
}

export interface FinalMessage {
  type: 'final';
  home_score: number;
  away_score: number;
  recorded_home_goals: number;
  recorded_away_goals: number;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export type ReplayMessage =
  | StateMessage
  | ProbabilityMessage
  | GoalMessage
  | FinalMessage
  | ErrorMessage;

export type ReplayStatus = 'idle' | 'connecting' | 'live' | 'finished' | 'error';

export interface ReplayState {
  status: ReplayStatus;
  error: string | null;
  initial: StateMessage | null;
  probabilities: ProbabilityMessage[];
  goals: GoalMessage[];
  final: FinalMessage | null;
}

const EMPTY_STATE: ReplayState = {
  status: 'idle',
  error: null,
  initial: null,
  probabilities: [],
  goals: [],
  final: null,
};

export interface UseReplayOptions {
  matchId: number | null;
  secondsPerMinute?: number;
  autoStart?: boolean;
}

export interface UseReplayResult extends ReplayState {
  start: () => void;
  stop: () => void;
}

/** Connect to the replay WebSocket and accumulate the messages it emits. */
export function useReplay({
  matchId,
  secondsPerMinute = 0.5,
  autoStart = false,
}: UseReplayOptions): UseReplayResult {
  const [state, setState] = useState<ReplayState>(EMPTY_STATE);
  const [runToken, setRunToken] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  const start = () => setRunToken((token) => token + 1);
  const stop = () => socketRef.current?.close();

  useEffect(() => {
    if (matchId === null) return;
    if (!autoStart && runToken === 0) return;

    setState({ ...EMPTY_STATE, status: 'connecting' });

    const url = `${WS_URL}/ws/matches/${matchId}/replay?seconds_per_minute=${secondsPerMinute}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      setState((previous) => ({ ...previous, status: 'live' }));
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as ReplayMessage;
        setState((previous) => applyMessage(previous, message));
      } catch {
        setState((previous) => ({ ...previous, status: 'error', error: 'Bad message from server' }));
      }
    };

    socket.onerror = () => {
      setState((previous) =>
        previous.status === 'finished'
          ? previous
          : { ...previous, status: 'error', error: 'Connection failed' },
      );
    };

    socket.onclose = () => {
      setState((previous) =>
        previous.status === 'live' ? { ...previous, status: 'finished' } : previous,
      );
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [matchId, autoStart, runToken, secondsPerMinute]);

  return { ...state, start, stop };
}

function applyMessage(state: ReplayState, message: ReplayMessage): ReplayState {
  switch (message.type) {
    case 'state':
      return { ...state, initial: message };
    case 'probability':
      return { ...state, probabilities: [...state.probabilities, message] };
    case 'goal':
      return { ...state, goals: [...state.goals, message] };
    case 'final':
      return { ...state, final: message, status: 'finished' };
    case 'error':
      return { ...state, status: 'error', error: message.message };
  }
}

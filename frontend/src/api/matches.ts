import { API_URL } from '../config';

export interface Team {
  team_api_id: number;
  long_name: string;
  short_name: string;
}

export interface MatchSummary {
  match_api_id: number;
  league_id: number;
  season: string;
  match_date: string;
  stage: number;
  home: Team;
  away: Team;
  home_goals: number;
  away_goals: number;
}

export interface MatchListResponse {
  season: string;
  matches: MatchSummary[];
}

export interface ProbabilityTriple {
  home: number;
  draw: number;
  away: number;
}

export interface PredictionResponse {
  match_api_id: number;
  always_home_baseline: ProbabilityTriple;
  bet365_odds_baseline: ProbabilityTriple | null;
  logistic_regression: ProbabilityTriple;
  gradient_boosting: ProbabilityTriple;
}

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} on ${path}`);
  }
  return (await response.json()) as T;
}

export function listMatches(
  season: string,
  options: { leagueId?: number; limit?: number; signal?: AbortSignal } = {},
): Promise<MatchListResponse> {
  const params = new URLSearchParams({ season });
  if (options.leagueId !== undefined) params.set('league_id', String(options.leagueId));
  params.set('limit', String(options.limit ?? 100));
  return requestJson<MatchListResponse>(`/matches?${params.toString()}`, options.signal);
}

export function getMatch(id: number, signal?: AbortSignal): Promise<MatchSummary> {
  return requestJson<MatchSummary>(`/matches/${id}`, signal);
}

export function getPrediction(id: number, signal?: AbortSignal): Promise<PredictionResponse> {
  return requestJson<PredictionResponse>(`/matches/${id}/prediction`, signal);
}

import { API_URL } from '../config';

export interface HealthStatus {
  status: 'ok' | 'degraded';
  database: 'ok' | 'unavailable';
}

export function isHealthStatus(value: unknown): value is HealthStatus {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    (candidate.status === 'ok' || candidate.status === 'degraded') &&
    (candidate.database === 'ok' || candidate.database === 'unavailable')
  );
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthStatus> {
  const response = await fetch(`${API_URL}/health`, { signal });

  // A 503 still carries a valid body describing which dependency is down.
  if (!response.ok && response.status !== 503) {
    throw new Error(`Health check failed with HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  if (!isHealthStatus(body)) {
    throw new Error('Health check returned an unexpected response');
  }
  return body;
}

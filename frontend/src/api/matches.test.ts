import { describe, expect, it, vi } from 'vitest';

import { getPrediction, listMatches } from './matches';

function stubFetch(implementation: (url: string) => Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => implementation(String(input)));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('listMatches', () => {
  it('encodes season, league and limit into the query string', async () => {
    const fetchMock = stubFetch(async () => jsonResponse({ season: '2015/2016', matches: [] }));

    await listMatches('2015/2016', { leagueId: 7, limit: 25 });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/matches?season=2015%2F2016&league_id=7&limit=25'),
      expect.anything(),
    );
  });

  it('defaults limit to 100 and omits the league filter', async () => {
    const fetchMock = stubFetch(async () => jsonResponse({ season: '2015/2016', matches: [] }));

    await listMatches('2015/2016');

    const requestedUrl = String(fetchMock.mock.calls[0]?.[0] ?? '');
    expect(requestedUrl).toContain('limit=100');
    expect(requestedUrl).not.toContain('league_id');
  });

  it('throws on HTTP errors', async () => {
    stubFetch(async () => new Response('boom', { status: 500 }));

    await expect(listMatches('2015/2016')).rejects.toThrow('HTTP 500');
  });
});

describe('getPrediction', () => {
  it('returns parsed JSON for a successful response', async () => {
    const body = {
      match_api_id: 1,
      always_home_baseline: { home: 1, draw: 0, away: 0 },
      bet365_odds_baseline: null,
      logistic_regression: { home: 0.5, draw: 0.3, away: 0.2 },
      gradient_boosting: { home: 0.45, draw: 0.3, away: 0.25 },
    };
    stubFetch(async () => jsonResponse(body));

    const prediction = await getPrediction(1);

    expect(prediction.match_api_id).toBe(1);
    expect(prediction.bet365_odds_baseline).toBeNull();
    expect(prediction.logistic_regression.home).toBe(0.5);
  });
});

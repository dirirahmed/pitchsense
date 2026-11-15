import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import App from './App';

function stubFetch(implementation: () => Promise<Response>) {
  const fetchMock = vi.fn(implementation);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('App', () => {
  it('shows a loading state before the health check resolves', () => {
    stubFetch(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByRole('status')).toHaveTextContent('Connecting to the API');
  });

  it('shows the API as connected when healthy', async () => {
    const fetchMock = stubFetch(async () => jsonResponse({ status: 'ok', database: 'ok' }));

    render(<App />);

    expect(await screen.findByText('API connected')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/health$/),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('shows a degraded state when the database is unavailable', async () => {
    stubFetch(async () => jsonResponse({ status: 'degraded', database: 'unavailable' }, 503));

    render(<App />);

    expect(await screen.findByText(/database unavailable/)).toBeInTheDocument();
  });

  it('shows an error when the API cannot be reached', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch');
    });

    render(<App />);

    expect(await screen.findByText('API unreachable: Failed to fetch')).toBeInTheDocument();
  });
});

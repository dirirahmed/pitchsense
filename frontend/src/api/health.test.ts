import { describe, expect, it, vi } from 'vitest';

import { fetchHealth, isHealthStatus } from './health';

describe('isHealthStatus', () => {
  it('accepts a valid payload', () => {
    expect(isHealthStatus({ status: 'ok', database: 'ok' })).toBe(true);
  });

  it.each([null, 'ok', {}, { status: 'ok' }, { status: 'fine', database: 'ok' }])(
    'rejects %j',
    (value) => {
      expect(isHealthStatus(value)).toBe(false);
    },
  );
});

describe('fetchHealth', () => {
  it('throws on HTTP errors other than 503', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })));

    await expect(fetchHealth()).rejects.toThrow('HTTP 500');
  });

  it('throws when the body has an unexpected shape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ hello: 'world' }))));

    await expect(fetchHealth()).rejects.toThrow('unexpected response');
  });
});

import { describe, expect, it } from 'vitest';
import { authRequestSchema, authResponseSchema } from '../src/index.js';

describe('authentication messages', () => {
  it('accepts a valid auth request', () => {
    const parsed = authRequestSchema.parse({
      type: 'auth',
      version: 1,
      token: 'secret-token',
      clientId: 'dsh-plugin',
      protocolVersion: 1,
    });
    expect(parsed.clientId).toBe('dsh-plugin');
  });

  it('rejects an empty token', () => {
    expect(() =>
      authRequestSchema.parse({
        type: 'auth',
        version: 1,
        token: '',
        clientId: 'dsh-plugin',
        protocolVersion: 1,
      }),
    ).toThrow();
  });

  it('parses auth.ok and auth.error', () => {
    expect(
      authResponseSchema.parse({ type: 'auth.ok', protocolVersion: 1, runtimeVersion: '0.1.0' })
        .type,
    ).toBe('auth.ok');
    expect(
      authResponseSchema.parse({
        type: 'auth.error',
        code: 'auth_failed',
        message: 'bad token',
      }).type,
    ).toBe('auth.error');
  });
});

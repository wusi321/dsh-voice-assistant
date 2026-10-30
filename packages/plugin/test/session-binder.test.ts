import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import type { DshAgent, DshAgentService } from '../src/host/dsh-types.js';
import { SessionBinder } from '../src/host/session-binder.js';

const config: Config = {
  autoStart: false,
  runtimeCommand: 'voice-runtime',
  discoveryPath: '/tmp/runtime.json',
  startupTimeoutMs: 1_000,
  reconnectMinMs: 100,
  reconnectMaxMs: 1_000,
  fakeAudio: true,
  statusRoute: true,
  sessionStrategy: 'active',
  fixedSessionId: '',
  cancelTimeoutMs: 1_000,
  speakAssistant: true,
};

function agent(id: string): DshAgent {
  return {
    id,
    status: 'idle',
    session: { id },
    followup: vi.fn(),
    steer: vi.fn(),
    cancel: vi.fn(),
    whenIdle: async () => {},
  };
}

function context(agents: DshAgentService): any {
  return {
    agents,
    effect: vi.fn(),
    on: vi.fn(),
    get: vi.fn(),
  };
}

describe('SessionBinder', () => {
  it('uses the client-reported active session when live', () => {
    const a = agent('s1');
    const service: DshAgentService = {
      get: (id) => (id === 's1' ? a : undefined),
      list: () => [a],
      roots: () => [a],
    };
    const binder = new SessionBinder(context(service), config);
    expect(binder.setActive('s1').live).toBe(true);
    expect(binder.resolve()?.id).toBe('s1');
    expect(binder.status().source).toBe('client');
  });

  it('does not silently fall back from a stale active id', () => {
    const a = agent('s1');
    const service: DshAgentService = {
      get: () => undefined,
      list: () => [a],
      roots: () => [a],
    };
    const binder = new SessionBinder(context(service), config);
    binder.setActive('deleted');
    expect(binder.resolve()).toBeUndefined();
    expect(binder.status().live).toBe(false);
  });

  it('uses the last root in last-session mode', () => {
    const a = agent('s1');
    const b = agent('s2');
    const service: DshAgentService = {
      get: (id) => [a, b].find((item) => item.id === id),
      list: () => [a, b],
      roots: () => [a, b],
    };
    const binder = new SessionBinder(context(service), { ...config, sessionStrategy: 'last' });
    expect(binder.resolve()?.id).toBe('s2');
  });

  it('uses a fixed session id', () => {
    const a = agent('fixed');
    const service: DshAgentService = {
      get: (id) => (id === 'fixed' ? a : undefined),
      list: () => [a],
      roots: () => [a],
    };
    const binder = new SessionBinder(context(service), {
      ...config,
      sessionStrategy: 'fixed',
      fixedSessionId: 'fixed',
    });
    expect(binder.resolve()?.id).toBe('fixed');
    expect(binder.status().source).toBe('fixed');
  });
});

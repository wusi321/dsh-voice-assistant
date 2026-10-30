import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import { apply } from '../src/host/index.js';

const config: Config = {
  autoStart: false,
  runtimeCommand: 'voice-runtime',
  discoveryPath: '/definitely/not/a/runtime.json',
  startupTimeoutMs: 100,
  reconnectMinMs: 100,
  reconnectMaxMs: 200,
  fakeAudio: true,
  statusRoute: true,
  sessionStrategy: 'active',
  fixedSessionId: '',
  cancelTimeoutMs: 1_000,
  speakAssistant: true,
};

describe('host plugin entry', () => {
  it('registers four effects and cleans up', () => {
    const cleanups: Array<() => void> = [];
    const ctx = {
      effect: (register: () => void | (() => void)) => {
        const cleanup = register();
        if (typeof cleanup === 'function') cleanups.push(cleanup);
        return () => {};
      },
      on: vi.fn(() => () => {}),
      get: vi.fn(),
      logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
    };

    apply(ctx as any, config);
    expect(cleanups).toHaveLength(4);
    for (const cleanup of cleanups) cleanup();
  });
});

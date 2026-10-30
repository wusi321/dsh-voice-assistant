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
  petEnabled: false,
  petBaseUrl: '',
  petId: 'main',
  petLockTtlMs: 1_000,
  petBridgeTimeoutMs: 1_000,
  petBubbleEnabled: true,
  petAnimationEnabled: true,
  petUseWorkStatus: true,
  petTtsProvider: false,
  petTtsProviderCommand: '',
};

describe('host plugin entry', () => {
  it('registers six effects and cleans up', () => {
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
    expect(cleanups).toHaveLength(6);
    for (const cleanup of cleanups) cleanup();
  });
});

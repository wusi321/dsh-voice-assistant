import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import type { DiscoveryInfo } from '../src/host/discovery.js';
import { RuntimeClient } from '../src/host/runtime-client.js';
import { RuntimeManager } from '../src/host/runtime-manager.js';

const config: Config = {
  autoStart: false,
  runtimeCommand: 'voice-runtime',
  discoveryPath: '/tmp/runtime.json',
  startupTimeoutMs: 1_000,
  reconnectMinMs: 100,
  reconnectMaxMs: 1_000,
  fakeAudio: false,
  statusRoute: true,
};

const info: DiscoveryInfo = {
  pid: 4242,
  host: '127.0.0.1',
  port: 9000,
  token: 'x'.repeat(32),
  runtimeVersion: '0.1.0',
  protocolVersion: 1,
  startedAt: '2026-10-30T00:00:00+00:00',
};

function context() {
  return {
    effect: vi.fn(),
    on: vi.fn(),
    get: vi.fn(),
    logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
  };
}

describe('RuntimeManager', () => {
  it('connects via discovery and reports connected status', async () => {
    const close = vi.fn();
    const manager = new RuntimeManager(context() as any, config, {
      readDiscovery: async () => info,
      isProcessAlive: () => true,
      connect: async (_info, options) => {
        options.onState?.('ready');
        return { close } as unknown as RuntimeClient;
      },
    });

    await manager.start();
    expect(manager.status.state).toBe('connected');
    expect(manager.status.port).toBe(9000);
    expect(manager.status.runtimeVersion).toBe('0.1.0');

    manager.stop();
    expect(close).toHaveBeenCalledOnce();
    expect(manager.status.state).toBe('stopped');
  });

  it('reports error when discovery is missing and autostart is off', async () => {
    const manager = new RuntimeManager(context() as any, config, {
      readDiscovery: async () => null,
      isProcessAlive: () => false,
    });
    await manager.start();
    expect(manager.status.state).toBe('error');
    expect(manager.status.detail).toContain('runtime discovery not found');
    manager.stop();
  });

  it('reconnects after a failed connection', async () => {
    vi.useFakeTimers();
    let attempts = 0;
    const close = vi.fn();
    const manager = new RuntimeManager(context() as any, config, {
      readDiscovery: async () => info,
      isProcessAlive: () => true,
      connect: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error('runtime offline');
        return { close } as unknown as RuntimeClient;
      },
    });
    await manager.start();
    expect(manager.status.state).toBe('error');
    await vi.advanceTimersByTimeAsync(150);
    expect(manager.status.state).toBe('connected');
    expect(attempts).toBe(2);
    manager.stop();
    vi.useRealTimers();
  });
});

import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import { PetBridge } from '../src/host/pet-bridge.js';

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
  petEnabled: true,
  petBaseUrl: 'http://127.0.0.1:3080',
  petId: 'main',
  petLockTtlMs: 60_000,
  petBridgeTimeoutMs: 1_000,
  petBubbleEnabled: true,
  petAnimationEnabled: true,
  petUseWorkStatus: true,
  petTtsProvider: false,
  petTtsProviderCommand: '',
};

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setup() {
  const calls: string[] = [];
  let textListener: ((text: string) => void) | undefined;
  const fetcher = vi.fn(async (input: URL | RequestInfo, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push(`${init?.method ?? 'GET'} ${url.pathname}${url.search}`);
    if (url.pathname.endsWith('/state')) {
      return json({ counter: 1, sections: {}, pets: { main: {} } });
    }
    if (url.pathname.endsWith('/lock/release')) return json({ ok: true, released: true });
    if (url.pathname.endsWith('/lock')) {
      return json({ ok: true, lockId: 'lk1', expiresAt: Date.now() + 60_000 });
    }
    if (url.pathname.endsWith('/work-status')) return json({ ok: true, state: 'thinking' });
    if (url.pathname.endsWith('/broadcast')) return json({ ok: true });
    if (url.pathname.endsWith('/anim')) return json({ ok: true, playbackId: 'p1' });
    if (url.pathname.endsWith('/wake') || url.pathname.endsWith('/sleep'))
      return json({ ok: true });
    return json({ ok: false, reason: 'not-found' }, 404);
  });
  const bridge: any = {
    status: { toolName: undefined },
    onStatus: vi.fn(() => () => {}),
  };
  const tts: any = {
    onStatus: vi.fn(() => () => {}),
    onText: vi.fn((listener: (text: string) => void) => {
      textListener = listener;
      return () => {};
    }),
  };
  const ctx: any = { get: vi.fn(), webServer: { port: 3080 }, effect: vi.fn(), on: vi.fn() };
  const pet = new PetBridge(ctx, config, bridge, tts, { fetch: fetcher as typeof fetch });
  return { pet, calls, fetcher, bridge, tts, getText: () => textListener };
}

describe('PetBridge', () => {
  it('probes /state and acquires a lock before a bubble', async () => {
    const { pet, calls } = setup();
    await pet.start();
    expect(pet.status.connection).toBe('available');
    const result = await pet.broadcast('你好', { duration: 3_000, anim: true });
    expect(result.ok).toBe(true);
    expect(calls[0]).toContain('/state');
    expect(calls.some((call) => call.includes('/lock'))).toBe(true);
    expect(calls.some((call) => call.includes('/broadcast') && call.includes('lock=lk1'))).toBe(
      true,
    );
    expect(pet.status.locked).toBe(true);
    await pet.stop();
  });

  it('wakes and sleeps under the lock', async () => {
    const { pet, calls } = setup();
    await pet.start();
    expect((await pet.wake()).ok).toBe(true);
    expect((await pet.sleep()).ok).toBe(true);
    expect(calls.some((call) => call.includes('/wake') && call.includes('lock=lk1'))).toBe(true);
    expect(calls.some((call) => call.includes('/sleep') && call.includes('lock=lk1'))).toBe(true);
    await pet.stop();
  });

  it('renews and releases a lock', async () => {
    const { pet, calls } = setup();
    await pet.start();
    expect(await pet.acquireLock(30_000)).toBe(true);
    expect(await pet.renewLock()).toBe(true);
    expect(calls.filter((call) => call.includes('/lock?')).length).toBeGreaterThanOrEqual(2);
    await pet.releaseLock();
    expect(calls.some((call) => call.includes('/lock/release'))).toBe(true);
    await pet.stop();
  });

  it('plays animations and writes work status', async () => {
    const { pet, calls } = setup();
    await pet.start();
    expect((await pet.playAnimation({ name: '待机' })).ok).toBe(true);
    expect((await pet.setWorkStatus('working', 'bash')).ok).toBe(true);
    expect(calls.some((call) => call.includes('/anim') && call.includes('lock=lk1'))).toBe(true);
    expect(calls.some((call) => call.includes('/work-status'))).toBe(true);
    await pet.stop();
  });

  it('turns assistant speech into a bubble', async () => {
    const { pet, calls, getText } = setup();
    await pet.start();
    getText()?.('这是气泡');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls.some((call) => call.includes('/broadcast'))).toBe(true);
    await pet.stop();
  });

  it('reports unavailable when dsh-pet is absent', async () => {
    const { pet, fetcher } = setup();
    fetcher.mockResolvedValueOnce(json({ error: 'not found' }, 404));
    await pet.start();
    expect(pet.status.connection).toBe('unavailable');
    expect(await pet.broadcast('hi')).toMatchObject({ ok: false, reason: 'unavailable' });
    await pet.stop();
  });
});

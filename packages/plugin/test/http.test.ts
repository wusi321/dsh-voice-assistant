import { Readable } from 'node:stream';

import { describe, expect, it, vi } from 'vitest';

import { registerStatusRoute } from '../src/host/http.js';
import type { Config } from '../src/host/config.js';
import type { DshAgent } from '../src/host/dsh-types.js';
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

function agent(id: string): DshAgent {
  return {
    id,
    status: 'running',
    session: { id },
    followup: vi.fn(),
    steer: vi.fn(),
    cancel: vi.fn(),
    whenIdle: async () => {},
  };
}

function response() {
  const value: { status?: number; body?: unknown } = {};
  return {
    value,
    res: {
      writeHead: (status: number) => {
        value.status = status;
      },
      end: (body: string) => {
        value.body = JSON.parse(body);
      },
    },
  };
}

function request(method: string, url: string, body?: unknown) {
  const stream = Readable.from(body === undefined ? [] : [Buffer.from(JSON.stringify(body))]);
  Object.assign(stream, { method, url });
  return stream;
}

describe('HTTP routes', () => {
  it('reports status and accepts the active session', async () => {
    const a = agent('s1');
    const ctx: any = {
      effect: vi.fn(),
      on: vi.fn(),
      get: vi.fn(),
      agents: {
        get: (id: string) => (id === 's1' ? a : undefined),
        list: () => [a],
        roots: () => [a],
      },
      webServer: { register: vi.fn() },
    };
    let handler: any;
    ctx.webServer.register = vi.fn((route: any) => {
      handler = route.handler;
      return () => {};
    });
    const binder = new SessionBinder(ctx, config);
    const manager: any = {
      status: { state: 'connected', discoveryPath: '/tmp/runtime.json', runtimeVersion: '0.1.0' },
    };
    const bridge: any = { status: { sessionId: null, agentState: 'IDLE' } };
    const tts: any = { status: { speaking: false } };
    const pet: any = {
      status: { connection: 'disabled', petId: 'main', locked: false, avatarState: 'idle' },
    };
    const petTts: any = { status: { state: 'disabled', reason: 'off' } };
    registerStatusRoute(ctx, manager, binder, bridge, tts, pet, petTts, true);

    const first = response();
    await handler(request('GET', '/dsh-voice-assistant/status'), first.res);
    expect(first.value.status).toBe(200);
    expect((first.value.body as any).session.sessionId).toBe('s1');

    const second = response();
    await handler(
      request('POST', '/dsh-voice-assistant/active-session', { sessionId: 's1' }),
      second.res,
    );
    expect(second.value.status).toBe(200);
    expect((second.value.body as any).ok).toBe(true);
    expect(binder.status().sessionId).toBe('s1');

    const third = response();
    await handler(request('GET', '/dsh-voice-assistant/status'), third.res);
    expect((third.value.body as any).session.live).toBe(true);
  });

  it('rejects a missing session id and unknown routes', async () => {
    const ctx: any = {
      effect: vi.fn(),
      on: vi.fn(),
      get: vi.fn(),
      agents: undefined,
      webServer: { register: vi.fn() },
    };
    let handler: any;
    ctx.webServer.register = vi.fn((route: any) => {
      handler = route.handler;
      return () => {};
    });
    const binder = new SessionBinder(ctx, config);
    registerStatusRoute(ctx, {} as any, binder, {} as any, {} as any, {} as any, {} as any, true);

    const missing = response();
    await handler(request('POST', '/dsh-voice-assistant/active-session', {}), missing.res);
    expect(missing.value.status).toBe(400);

    const unknown = response();
    await handler(request('GET', '/dsh-voice-assistant/nope'), unknown.res);
    expect(unknown.value.status).toBe(404);
  });
});

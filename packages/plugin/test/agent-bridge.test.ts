import { describe, expect, it, vi } from 'vitest';

import { DshAgentBridge } from '../src/host/agent-bridge.js';
import type { Config } from '../src/host/config.js';
import type { DshAgent, DshAgentService } from '../src/host/dsh-types.js';
import { SessionBinder } from '../src/host/session-binder.js';
import type { TtsOutput } from '../src/host/tts-output.js';

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

function makeAgent(id = 's1'): DshAgent {
  return {
    id,
    status: 'running',
    session: { id },
    followup: vi.fn(),
    steer: vi.fn(),
    cancel: vi.fn(),
    whenIdle: vi.fn(async () => {}),
  };
}

function makeContext(a: DshAgent) {
  const handlers = new Map<string, (...args: any[]) => void>();
  const service: DshAgentService = {
    get: (id) => (id === a.id ? a : undefined),
    list: () => [a],
    roots: () => [a],
  };
  const ctx = {
    agents: service,
    effect: vi.fn(),
    get: vi.fn(),
    on: vi.fn((event: string, handler: (...args: any[]) => void) => {
      handlers.set(event, handler);
      return () => handlers.delete(event);
    }),
  };
  return { ctx, handlers };
}

function makeBridge(a: DshAgent, tts: any) {
  const { ctx, handlers } = makeContext(a);
  const binder = new SessionBinder(ctx as any, config);
  binder.setActive(a.id);
  const bridge = new DshAgentBridge(ctx as any, binder, tts as TtsOutput, config);
  bridge.subscribe();
  return { bridge, binder, handlers, ctx };
}

describe('DshAgentBridge', () => {
  it('sends a voice message through agent.followup', () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge } = makeBridge(a, tts);
    expect(bridge.sendMessage('打开台灯')).toBe('s1');
    expect(a.followup).toHaveBeenCalledOnce();
    const message = vi.mocked(a.followup).mock.calls[0]?.[0] as any;
    expect(message.role).toBe('user');
    expect(message.content[0].text).toBe('打开台灯');
    expect(message.source.kind).toBe('user');
  });

  it('speaks only text deltas and ignores reasoning/tool argument deltas', () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge, handlers } = makeBridge(a, tts);
    const stream = handlers.get('agent/assistant-stream');
    expect(stream).toBeDefined();
    stream?.({
      agent: a,
      frame: { type: 'chunk', chunk: { type: 'reasoning-delta', text: '秘密推理' } },
    });
    stream?.({
      agent: a,
      frame: { type: 'chunk', chunk: { type: 'tool-call-delta', argumentsDelta: '{}' } },
    });
    stream?.({ agent: a, frame: { type: 'chunk', chunk: { type: 'text-delta', text: '你好。' } } });
    stream?.({ agent: a, frame: { type: 'end' } });
    expect(tts.speak).toHaveBeenCalledTimes(1);
    expect(tts.speak).toHaveBeenCalledWith('你好。');
    expect(bridge.status.agentState).toBe('IDLE');
  });

  it('derives tool status from session events', () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge, handlers } = makeBridge(a, tts);
    const sessionEvent = handlers.get('session/event');
    sessionEvent?.({ id: 's1' }, { type: 'tool/call', data: { name: 'bash' } });
    expect(bridge.status.agentState).toBe('TOOL_RUNNING');
    expect(bridge.status.toolName).toBe('bash');
    sessionEvent?.({ id: 's1' }, { type: 'tool/result', data: {} });
    expect(bridge.status.agentState).toBe('THINKING');
    sessionEvent?.({ id: 's1' }, { type: 'turn/end', data: { reason: { kind: 'completed' } } });
    expect(bridge.status.agentState).toBe('SUCCESS');
  });

  it('ignores events from another session', () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge, handlers } = makeBridge(a, tts);
    handlers.get('agent/assistant-stream')?.({
      agent: { ...a, id: 'other' },
      frame: { type: 'chunk', chunk: { type: 'text-delta', text: '不应播报。' } },
    });
    expect(tts.speak).not.toHaveBeenCalled();
    expect(bridge.status.sessionId).toBe('s1');
  });

  it('cancels with keepInbox and waits for idle', async () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge } = makeBridge(a, tts);
    await expect(bridge.cancelCurrentTurn()).resolves.toBe('cancelled');
    expect(a.cancel).toHaveBeenCalledWith({ kind: 'user' }, { keepInbox: true });
    expect(a.whenIdle).toHaveBeenCalledOnce();
    expect(bridge.status.agentState).toBe('CANCELLED');
  });

  it('routes speech.final and session.interrupt from the Runtime', async () => {
    const a = makeAgent();
    const tts = { speak: vi.fn(), cancel: vi.fn() };
    const { bridge } = makeBridge(a, tts);
    bridge.handleRuntimeEvent({
      version: 1,
      id: 'e1',
      sessionId: 's1',
      sequence: 1,
      timestamp: 1,
      type: 'speech.final',
      payload: { utteranceId: 'u1', text: '你好' },
    });
    expect(a.followup).toHaveBeenCalledOnce();
    bridge.handleRuntimeEvent({
      version: 1,
      id: 'e2',
      sessionId: 's1',
      sequence: 2,
      timestamp: 2,
      type: 'session.interrupt',
      payload: { action: 'tts' },
    });
    expect(tts.cancel).toHaveBeenCalledWith('user_stop');
  });
});

import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import type { AnyVoiceEvent } from '@dsh-voice/protocol';
import { TtsOutput } from '../src/host/tts-output.js';

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

function context() {
  return { effect: vi.fn(), on: vi.fn(), get: vi.fn() } as any;
}

function manager(connected = true) {
  return {
    connected,
    send: vi.fn(() => connected),
  } as any;
}

function event(type: string, payload: Record<string, unknown>): AnyVoiceEvent {
  return {
    version: 1,
    id: 'e1',
    sessionId: 's1',
    sequence: 1,
    timestamp: 1,
    type: type as any,
    payload,
  } as AnyVoiceEvent;
}

describe('TtsOutput', () => {
  it('sends tts.speak only when the Runtime is connected', () => {
    const down = new TtsOutput(context(), manager(false), config);
    expect(down.speak('hello.')).toBe(false);

    const send = vi.fn(() => true);
    const up = new TtsOutput(context(), { connected: true, send } as any, config);
    expect(up.speak('hello.')).toBe(true);
    expect(send).toHaveBeenCalledWith(
      'tts.speak',
      expect.objectContaining({ text: 'hello.', interruptible: true }),
    );
    expect(up.status.speaking).toBe(true);
  });

  it('tracks started/finished/interrupted', () => {
    const tts = new TtsOutput(context(), manager(), config);
    tts.speak('first.');
    const id = tts.status.utteranceId;
    expect(id).toBeTruthy();
    tts.handleRuntimeEvent(event('tts.started', { utteranceId: id }));
    expect(tts.status.speaking).toBe(true);
    tts.handleRuntimeEvent(event('tts.finished', { utteranceId: id }));
    expect(tts.status.speaking).toBe(false);
  });

  it('cancels the active utterance', () => {
    const send = vi.fn(() => true);
    const tts = new TtsOutput(context(), { connected: true, send } as any, config);
    tts.speak('stop.');
    tts.cancel('barge_in');
    expect(send).toHaveBeenCalledWith(
      'tts.cancel',
      expect.objectContaining({ reason: 'barge_in' }),
    );
    expect(tts.status.speaking).toBe(false);
  });
});

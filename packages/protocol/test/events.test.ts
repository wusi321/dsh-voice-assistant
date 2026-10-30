import { describe, expect, it } from 'vitest';
import {
  PROTOCOL_VERSION,
  VOICE_EVENT_VERSION,
  parseVoiceEvent,
  tryParseVoiceEvent,
  voiceEventSchema,
} from '../src/index.js';

const base = {
  version: VOICE_EVENT_VERSION,
  id: 'evt-1',
  sessionId: 'session-1',
  sequence: 0,
  timestamp: 1_700_000_000_000,
};

describe('voice event envelope', () => {
  it('parses runtime.ready', () => {
    const event = parseVoiceEvent({
      ...base,
      type: 'runtime.ready',
      payload: {
        runtimeVersion: '0.1.0',
        protocolVersion: PROTOCOL_VERSION,
        capabilities: ['vad', 'asr', 'tts'],
      },
    });
    expect(event.type).toBe('runtime.ready');
    if (event.type !== 'runtime.ready') throw new Error('expected runtime.ready');
    expect(event.payload.protocolVersion).toBe(1);
  });

  it('parses a plugin command', () => {
    const event = parseVoiceEvent({
      ...base,
      type: 'tts.speak',
      payload: { utteranceId: 'u-1', text: '你好', interruptible: true },
    });
    expect(event.type).toBe('tts.speak');
  });

  it('rejects an unknown event type', () => {
    expect(tryParseVoiceEvent({ ...base, type: 'does.not.exist', payload: {} })).toBeNull();
  });

  it('rejects a negative sequence', () => {
    const result = voiceEventSchema.safeParse({
      ...base,
      sequence: -1,
      type: 'ping',
      payload: { pingId: 'p-1' },
    });
    expect(result.success).toBe(false);
  });

  it('rejects a missing sessionId', () => {
    const { sessionId: _sessionId, ...withoutSession } = base;
    const result = voiceEventSchema.safeParse({
      ...withoutSession,
      type: 'ping',
      payload: { pingId: 'p-1' },
    });
    expect(result.success).toBe(false);
  });

  it('enforces the tts.speak text limit', () => {
    const result = voiceEventSchema.safeParse({
      ...base,
      type: 'tts.speak',
      payload: { utteranceId: 'u-1', text: 'x'.repeat(4001) },
    });
    expect(result.success).toBe(false);
  });
});

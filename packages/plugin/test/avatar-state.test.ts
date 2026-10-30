import { describe, expect, it } from 'vitest';

import { deriveAvatarState, toPetWorkStatus } from '../src/host/avatar-state.js';

describe('avatar state', () => {
  it('does not let Voice IDLE hide an Agent tool call', () => {
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'TOOL_RUNNING' })).toBe('working');
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'THINKING' })).toBe('thinking');
  });

  it('gives errors and confirmations priority', () => {
    expect(
      deriveAvatarState({ voiceState: 'SPEAKING', agentState: 'ERROR', ttsSpeaking: true }),
    ).toBe('error');
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'WAITING_CONFIRMATION' })).toBe(
      'waiting',
    );
  });

  it('uses speaking only when the Agent is idle', () => {
    expect(deriveAvatarState({ voiceState: 'IDLE', ttsSpeaking: true })).toBe('speaking');
    expect(
      deriveAvatarState({ voiceState: 'SPEAKING', agentState: 'TOOL_RUNNING', ttsSpeaking: true }),
    ).toBe('working');
  });

  it('maps listening and terminal states', () => {
    expect(deriveAvatarState({ voiceState: 'LISTENING' })).toBe('listening');
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'TOOL_RESULT' })).toBe('result');
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'SUCCESS' })).toBe('success');
    expect(deriveAvatarState({ voiceState: 'IDLE', agentState: 'CANCELLED' })).toBe('idle');
  });

  it('maps only the six dsh-pet work states', () => {
    expect(toPetWorkStatus('thinking')).toBe('thinking');
    expect(toPetWorkStatus('working')).toBe('working');
    expect(toPetWorkStatus('waiting')).toBe('waiting');
    expect(toPetWorkStatus('success')).toBe('success');
    expect(toPetWorkStatus('error')).toBe('error');
    expect(toPetWorkStatus('speaking')).toBeNull();
    expect(toPetWorkStatus('idle')).toBeNull();
  });
});

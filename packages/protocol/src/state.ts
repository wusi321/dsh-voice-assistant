import { z } from 'zod';

/**
 * Voice Runtime state. Independent from Agent state and Avatar state.
 * See docs/PROTOCOL.md for the transition table.
 */
export const VOICE_STATES = [
  'IDLE',
  'WAKEUP',
  'LISTENING',
  'TRANSCRIBING',
  'DISPATCHING',
  'THINKING',
  'SPEAKING',
  'INTERRUPTING',
  'CONFIRMATION',
  'ERROR',
] as const;

/** DSH Agent state, derived from Session/Agent events; never owned by the Runtime. */
export const AGENT_STATES = [
  'IDLE',
  'THINKING',
  'TOOL_CALLING',
  'TOOL_RUNNING',
  'WAITING_CONFIRMATION',
  'SUCCESS',
  'ERROR',
  'CANCELLED',
] as const;

/** Avatar presentation is a projection of Voice + Agent state, not a third source of truth. */
export const AVATAR_STATES = [
  'IDLE',
  'LISTENING',
  'THINKING',
  'WORKING',
  'SPEAKING',
  'CONFIRMATION',
  'SUCCESS',
  'ERROR',
] as const;

export const voiceStateSchema = z.enum(VOICE_STATES);
export const agentStateSchema = z.enum(AGENT_STATES);
export const avatarStateSchema = z.enum(AVATAR_STATES);

export type VoiceState = z.infer<typeof voiceStateSchema>;
export type AgentState = z.infer<typeof agentStateSchema>;
export type AvatarState = z.infer<typeof avatarStateSchema>;

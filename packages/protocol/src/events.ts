import { z } from 'zod';
import { agentStateSchema, voiceStateSchema } from './state.js';
import { VOICE_EVENT_VERSION } from './version.js';

/**
 * Event envelope shared by every JSON control message.
 *
 * `sessionId` is the DSH Session the voice turn is bound to. `sequence` is a
 * per-session monotonic counter assigned by the sender; the receiver must
 * reject duplicates and gaps (except for explicitly resumable events).
 */
export interface VoiceEvent<T = unknown> {
  readonly version: typeof VOICE_EVENT_VERSION;
  readonly id: string;
  readonly sessionId: string;
  readonly sequence: number;
  readonly timestamp: number;
  readonly type: VoiceEventType;
  readonly payload: T;
}

const baseFields = {
  version: z.literal(VOICE_EVENT_VERSION),
  id: z.string().min(1).max(128),
  sessionId: z.string().min(1),
  sequence: z.number().int().nonnegative(),
  timestamp: z.number().int().nonnegative(),
};

/** Runtime -> Plugin: the Runtime is ready to accept authenticated commands. */
export const runtimeReadySchema = z.object({
  ...baseFields,
  type: z.literal('runtime.ready'),
  payload: z.object({
    runtimeVersion: z.string().min(1),
    protocolVersion: z.number().int().positive(),
    capabilities: z.array(z.string().min(1)),
    audio: z
      .object({
        inputDevice: z.string().optional(),
        outputDevice: z.string().optional(),
        sampleRate: z.number().int().positive().optional(),
        channels: z.number().int().min(1).max(2).optional(),
      })
      .optional(),
  }),
});

/** Runtime -> Plugin: a fatal or non-fatal runtime error. */
export const runtimeErrorSchema = z.object({
  ...baseFields,
  type: z.literal('runtime.error'),
  payload: z.object({
    code: z.string().min(1),
    message: z.string().min(1),
    fatal: z.boolean(),
    detail: z.unknown().optional(),
  }),
});

/** Runtime -> Plugin: a wake word was accepted. */
export const wakeDetectedSchema = z.object({
  ...baseFields,
  type: z.literal('wake.detected'),
  payload: z.object({
    keyword: z.string().min(1),
    score: z.number().min(0).max(1),
  }),
});

/** Runtime -> Plugin: an utterance started. */
export const speechStartedSchema = z.object({
  ...baseFields,
  type: z.literal('speech.started'),
  payload: z.object({
    utteranceId: z.string().min(1),
    startedAtMs: z.number().int().nonnegative().optional(),
  }),
});

/** Runtime -> Plugin: a partial transcript. */
export const speechPartialSchema = z.object({
  ...baseFields,
  type: z.literal('speech.partial'),
  payload: z.object({
    utteranceId: z.string().min(1),
    text: z.string(),
    stability: z.number().min(0).max(1).optional(),
  }),
});

/** Runtime -> Plugin: the final transcript for one utterance. */
export const speechFinalSchema = z.object({
  ...baseFields,
  type: z.literal('speech.final'),
  payload: z.object({
    utteranceId: z.string().min(1),
    text: z.string(),
    language: z.string().optional(),
    durationMs: z.number().int().nonnegative().optional(),
  }),
});

/** Runtime -> Plugin: TTS playback started. */
export const ttsStartedSchema = z.object({
  ...baseFields,
  type: z.literal('tts.started'),
  payload: z.object({
    utteranceId: z.string().min(1),
    text: z.string(),
    sampleRate: z.number().int().positive(),
    channels: z.number().int().min(1).max(2),
  }),
});

/** Runtime -> Plugin: TTS playback finished naturally. */
export const ttsFinishedSchema = z.object({
  ...baseFields,
  type: z.literal('tts.finished'),
  payload: z.object({
    utteranceId: z.string().min(1),
    durationMs: z.number().int().nonnegative().optional(),
  }),
});

/** Runtime -> Plugin: TTS playback was interrupted. */
export const ttsInterruptedSchema = z.object({
  ...baseFields,
  type: z.literal('tts.interrupted'),
  payload: z.object({
    utteranceId: z.string().min(1),
    reason: z.enum(['barge_in', 'user_stop', 'cancel', 'error']),
  }),
});

/** Runtime -> Plugin: an audio device changed state. */
export const deviceChangedSchema = z.object({
  ...baseFields,
  type: z.literal('device.changed'),
  payload: z.object({
    kind: z.enum(['input', 'output', 'both']),
    state: z.enum(['connected', 'disconnected', 'changed']),
    deviceId: z.string().optional(),
    name: z.string().optional(),
  }),
});

/** Runtime -> Plugin: voice/agent state changed. */
export const sessionStateChangedSchema = z.object({
  ...baseFields,
  type: z.literal('session.state_changed'),
  payload: z.object({
    voiceState: voiceStateSchema,
    previousVoiceState: voiceStateSchema.optional(),
    agentState: agentStateSchema.optional(),
  }),
});

/** Runtime -> Plugin: health snapshot. */
export const runtimeHealthSchema = z.object({
  ...baseFields,
  type: z.literal('runtime.health'),
  payload: z.object({
    status: z.enum(['ok', 'degraded', 'error']),
    uptimeMs: z.number().int().nonnegative(),
    engines: z.record(z.string(), z.string()),
    queueDepth: z.number().int().nonnegative().optional(),
  }),
});

/** Runtime -> Plugin: heartbeat response. */
export const pongSchema = z.object({
  ...baseFields,
  type: z.literal('pong'),
  payload: z.object({
    pingId: z.string().min(1),
    receivedAt: z.number().int().nonnegative(),
  }),
});

/** Plugin -> Runtime: start listening. */
export const listenStartSchema = z.object({
  ...baseFields,
  type: z.literal('listen.start'),
  payload: z.object({
    mode: z.enum(['wake', 'push-to-talk']).optional(),
    boundSessionId: z.string().optional(),
  }),
});

/** Plugin -> Runtime: stop listening and finalize the current utterance. */
export const listenStopSchema = z.object({
  ...baseFields,
  type: z.literal('listen.stop'),
  payload: z.object({
    reason: z.string().optional(),
  }),
});

/** Plugin -> Runtime: cancel the current listening/utterance without dispatching. */
export const listenCancelSchema = z.object({
  ...baseFields,
  type: z.literal('listen.cancel'),
  payload: z.object({
    reason: z.string().optional(),
  }),
});

/** Plugin -> Runtime: synthesize and play text. */
export const ttsSpeakSchema = z.object({
  ...baseFields,
  type: z.literal('tts.speak'),
  payload: z.object({
    utteranceId: z.string().min(1),
    text: z.string().min(1).max(4000),
    voice: z.string().optional(),
    speed: z.number().positive().max(3).optional(),
    interruptible: z.boolean().optional(),
  }),
});

/** Plugin -> Runtime: cancel one or all TTS utterances. */
export const ttsCancelSchema = z.object({
  ...baseFields,
  type: z.literal('tts.cancel'),
  payload: z.object({
    utteranceId: z.string().optional(),
    reason: z.enum(['barge_in', 'user_stop', 'cancel', 'error']).optional(),
  }),
});

/** Plugin -> Runtime: interrupt semantics chosen by the user's intent. */
export const sessionInterruptSchema = z.object({
  ...baseFields,
  type: z.literal('session.interrupt'),
  payload: z.object({
    action: z.enum(['tts', 'agent', 'steer']),
    text: z.string().optional(),
    reason: z.string().optional(),
  }),
});

/** Plugin -> Runtime: update runtime configuration. */
export const configUpdateSchema = z.object({
  ...baseFields,
  type: z.literal('config.update'),
  payload: z.object({
    patch: z.record(z.string(), z.unknown()),
  }),
});

/** Plugin -> Runtime: graceful shutdown. */
export const runtimeShutdownSchema = z.object({
  ...baseFields,
  type: z.literal('runtime.shutdown'),
  payload: z.object({
    reason: z.string().optional(),
  }),
});

/** Plugin -> Runtime: heartbeat request. */
export const pingSchema = z.object({
  ...baseFields,
  type: z.literal('ping'),
  payload: z.object({
    pingId: z.string().min(1),
  }),
});

export const runtimeEventSchemas = [
  runtimeReadySchema,
  runtimeErrorSchema,
  wakeDetectedSchema,
  speechStartedSchema,
  speechPartialSchema,
  speechFinalSchema,
  ttsStartedSchema,
  ttsFinishedSchema,
  ttsInterruptedSchema,
  deviceChangedSchema,
  sessionStateChangedSchema,
  runtimeHealthSchema,
  pongSchema,
] as const;

export const pluginEventSchemas = [
  listenStartSchema,
  listenStopSchema,
  listenCancelSchema,
  ttsSpeakSchema,
  ttsCancelSchema,
  sessionInterruptSchema,
  configUpdateSchema,
  runtimeShutdownSchema,
  pingSchema,
] as const;

/** All control events, discriminated by `type`. */
export const voiceEventSchema = z.discriminatedUnion('type', [
  ...runtimeEventSchemas,
  ...pluginEventSchemas,
]);

export type RuntimeReadyEvent = z.infer<typeof runtimeReadySchema>;
export type RuntimeErrorEvent = z.infer<typeof runtimeErrorSchema>;
export type WakeDetectedEvent = z.infer<typeof wakeDetectedSchema>;
export type SpeechStartedEvent = z.infer<typeof speechStartedSchema>;
export type SpeechPartialEvent = z.infer<typeof speechPartialSchema>;
export type SpeechFinalEvent = z.infer<typeof speechFinalSchema>;
export type TtsStartedEvent = z.infer<typeof ttsStartedSchema>;
export type TtsFinishedEvent = z.infer<typeof ttsFinishedSchema>;
export type TtsInterruptedEvent = z.infer<typeof ttsInterruptedSchema>;
export type DeviceChangedEvent = z.infer<typeof deviceChangedSchema>;
export type SessionStateChangedEvent = z.infer<typeof sessionStateChangedSchema>;
export type RuntimeHealthEvent = z.infer<typeof runtimeHealthSchema>;
export type PongEvent = z.infer<typeof pongSchema>;
export type ListenStartEvent = z.infer<typeof listenStartSchema>;
export type ListenStopEvent = z.infer<typeof listenStopSchema>;
export type ListenCancelEvent = z.infer<typeof listenCancelSchema>;
export type TtsSpeakEvent = z.infer<typeof ttsSpeakSchema>;
export type TtsCancelEvent = z.infer<typeof ttsCancelSchema>;
export type SessionInterruptEvent = z.infer<typeof sessionInterruptSchema>;
export type ConfigUpdateEvent = z.infer<typeof configUpdateSchema>;
export type RuntimeShutdownEvent = z.infer<typeof runtimeShutdownSchema>;
export type PingEvent = z.infer<typeof pingSchema>;

export type AnyVoiceEvent = z.infer<typeof voiceEventSchema>;
export type VoiceEventType = AnyVoiceEvent['type'];

/**
 * Parse an untrusted JSON value into a typed control event.
 * The caller is responsible for the outer transport frame (text vs binary).
 */
export function parseVoiceEvent(value: unknown): AnyVoiceEvent {
  return voiceEventSchema.parse(value);
}

/** Safe variant: returns `null` instead of throwing. */
export function tryParseVoiceEvent(value: unknown): AnyVoiceEvent | null {
  const parsed = voiceEventSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

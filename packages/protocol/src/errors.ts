/** Stable error codes used by both sides of the voice protocol. */
export const VOICE_ERROR_CODES = [
  'auth_failed',
  'protocol_version_mismatch',
  'invalid_message',
  'unsupported_message',
  'session_missing',
  'engine_unavailable',
  'device_lost',
  'tts_cancelled',
  'agent_cancel_failed',
  'timeout',
  'internal',
] as const;

export type VoiceErrorCode = (typeof VOICE_ERROR_CODES)[number];

/** Error shape carried by `runtime.error` and returned by request handlers. */
export interface VoiceErrorPayload {
  readonly code: VoiceErrorCode;
  readonly message: string;
  readonly fatal: boolean;
  readonly detail?: unknown;
}

/** Typed error for protocol-level failures. */
export class VoiceProtocolError extends Error {
  readonly code: VoiceErrorCode;

  constructor(code: VoiceErrorCode, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'VoiceProtocolError';
    this.code = code;
  }
}

export function isVoiceErrorCode(value: unknown): value is VoiceErrorCode {
  return typeof value === 'string' && (VOICE_ERROR_CODES as readonly string[]).includes(value);
}

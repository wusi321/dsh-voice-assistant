/** Wire protocol version shared by the Runtime and the DSH plugin. */
export const PROTOCOL_VERSION = 1 as const;

/** Version carried by every JSON control event. */
export const VOICE_EVENT_VERSION = 1 as const;

/** Binary PCM frame magic. */
export const PCM_FRAME_MAGIC = 'VAP1';

/** Current binary frame header size in bytes. */
export const PCM_FRAME_HEADER_BYTES = 28;

/** PCM sample encoding identifiers. */
export const PCM_FORMAT = {
  PCM16_LE: 1,
} as const;

export type PcmFormat = (typeof PCM_FORMAT)[keyof typeof PCM_FORMAT];

import { z } from 'zod';
import { VOICE_EVENT_VERSION } from './version.js';

/** First client message on every WebSocket connection. */
export const authRequestSchema = z.object({
  type: z.literal('auth'),
  version: z.literal(VOICE_EVENT_VERSION),
  token: z.string().min(1).max(512),
  clientId: z.string().min(1).max(128),
  protocolVersion: z.number().int().positive(),
});

/** Successful authentication response. */
export const authOkSchema = z.object({
  type: z.literal('auth.ok'),
  protocolVersion: z.number().int().positive(),
  runtimeVersion: z.string().min(1),
});

/** Rejected authentication response; the server closes the connection afterwards. */
export const authErrorSchema = z.object({
  type: z.literal('auth.error'),
  code: z.enum(['auth_failed', 'protocol_version_mismatch', 'invalid_message']),
  message: z.string().min(1),
});

export const authResponseSchema = z.discriminatedUnion('type', [authOkSchema, authErrorSchema]);

export type AuthRequest = z.infer<typeof authRequestSchema>;
export type AuthOk = z.infer<typeof authOkSchema>;
export type AuthError = z.infer<typeof authErrorSchema>;
export type AuthResponse = z.infer<typeof authResponseSchema>;

import z from '@deepseek-ai/schemastery';

/** Plugin configuration. Empty string means "use the platform default". */
export const Config = z.object({
  autoStart: z.boolean().default(true),
  runtimeCommand: z.string().default('voice-runtime'),
  discoveryPath: z.string().default(''),
  startupTimeoutMs: z.natural().min(500).max(60_000).default(8_000),
  reconnectMinMs: z.natural().min(200).max(60_000).default(500),
  reconnectMaxMs: z.natural().min(500).max(120_000).default(15_000),
  fakeAudio: z.boolean().default(false),
  statusRoute: z.boolean().default(true),
  sessionStrategy: z.union(['active', 'fixed', 'last']).default('active'),
  fixedSessionId: z.string().default(''),
  cancelTimeoutMs: z.natural().min(500).max(120_000).default(8_000),
  speakAssistant: z.boolean().default(true),
});

export type Config = Schemastery.TypeT<typeof Config>;

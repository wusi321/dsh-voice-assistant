import { spawn } from 'node:child_process';

import type { Config } from './config.js';
import { log, type HostContext } from './types.js';

export interface PetVoiceProvider {
  readonly id: string;
  readonly name: string;
  synthesize(input: { readonly text: string; readonly rate: string }): Promise<Uint8Array>;
}

export interface PetVoiceApi {
  readonly voice?: {
    register(provider: PetVoiceProvider): () => void;
    list(): { builtin: string[]; external: string[] };
  };
}

export type PetTtsProviderState = 'disabled' | 'unsupported' | 'registered';

const PROVIDER_ID = 'dsh-voice-runtime';
const MAX_TEXT_CHARS = 500;
const TIMEOUT_MS = 15_000;

export type Mp3Synthesizer = (input: { text: string; rate: string }) => Promise<Uint8Array>;

/** Uses an explicitly configured local command: text on stdin, mp3 on stdout. */
export class CommandMp3Synthesizer {
  constructor(private readonly command: string) {}

  async synthesize(input: { text: string; rate: string }): Promise<Uint8Array> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.command, {
        shell: true,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, DSH_PET_TTS_RATE: input.rate },
      });
      const chunks: Buffer[] = [];
      let stderr = '';
      child.stdout.on('data', (chunk: Buffer) => chunks.push(chunk));
      child.stderr.on('data', (chunk: Buffer) => {
        if (stderr.length < 500) stderr += chunk.toString('utf8');
      });
      child.on('error', reject);
      child.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`mp3 command exited ${code}: ${stderr.slice(0, 200)}`));
          return;
        }
        const value = Buffer.concat(chunks);
        if (value.length === 0) {
          reject(new Error('mp3 command returned no bytes'));
          return;
        }
        resolve(new Uint8Array(value));
      });
      child.stdin.end(input.text);
    });
  }
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error('pet TTS provider timed out')), timeoutMs);
    timer.unref?.();
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function isLikelyMp3(bytes: Uint8Array): boolean {
  if (bytes.byteLength < 3) return false;
  // ID3v2 tag or an MPEG audio frame sync (0xFF 0xEx/0xFx).
  if (bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33) return true;
  return bytes[0] === 0xff && (bytes[1]! & 0xe0) === 0xe0;
}

/**
 * Optional dsh-pet TTS provider. The default is OFF: Voice Runtime is the sole
 * playback authority. It is only registered when a real MP3 synthesizer is
 * explicitly configured; this adapter never fabricates audio bytes.
 */
export class PetTtsProvider {
  private readonly ctx: HostContext;
  private readonly config: Config;
  private readonly synthesizer?: Mp3Synthesizer;
  private state: PetTtsProviderState = 'disabled';
  private reason = 'disabled by config';
  private dispose: (() => void) | null = null;

  constructor(ctx: HostContext, config: Config, synthesizer?: Mp3Synthesizer) {
    this.ctx = ctx;
    this.config = config;
    const commandSynth = config.petTtsProviderCommand
      ? new CommandMp3Synthesizer(config.petTtsProviderCommand)
      : undefined;
    this.synthesizer = synthesizer ?? commandSynth?.synthesize.bind(commandSynth);
  }

  get status(): { state: PetTtsProviderState; reason: string } {
    return { state: this.state, reason: this.reason };
  }

  start(): () => void {
    if (!this.config.petTtsProvider) {
      this.state = 'disabled';
      this.reason = 'disabled by config';
      return () => {};
    }
    const api = this.ctx.get<PetVoiceApi>('petApi7340', false);
    if (!api?.voice?.register) {
      this.state = 'unsupported';
      this.reason = 'dsh-pet petApi7340.voice.register is not available';
      return () => {};
    }
    if (!this.synthesizer) {
      this.state = 'unsupported';
      this.reason = 'no MP3 synthesizer configured (petTtsProviderCommand is empty)';
      return () => {};
    }
    const provider: PetVoiceProvider = {
      id: PROVIDER_ID,
      name: 'DSH Voice Runtime',
      synthesize: async (input) => {
        const text = input.text.trim();
        if (!text) throw new TypeError('text is required');
        if (text.length > MAX_TEXT_CHARS) {
          throw new RangeError(`text too long (max ${MAX_TEXT_CHARS} chars)`);
        }
        const bytes = await withTimeout(this.synthesizer!({ text, rate: input.rate }), TIMEOUT_MS);
        if (!(bytes instanceof Uint8Array) || bytes.byteLength === 0) {
          throw new TypeError('mp3 synthesizer returned no bytes');
        }
        if (!isLikelyMp3(bytes)) {
          throw new TypeError('mp3 synthesizer returned a non-MP3 payload');
        }
        return bytes;
      },
    };
    try {
      this.dispose = api.voice.register(provider);
    } catch (error) {
      this.state = 'unsupported';
      this.reason = error instanceof Error ? error.message : String(error);
      return () => {};
    }
    this.state = 'registered';
    this.reason = 'registered';
    log(this.ctx, 'info', 'dsh-pet TTS provider registered', { id: PROVIDER_ID });
    return () => this.stop();
  }

  stop(): void {
    this.dispose?.();
    this.dispose = null;
    if (this.state === 'registered') this.state = 'disabled';
    this.reason = 'stopped';
  }
}

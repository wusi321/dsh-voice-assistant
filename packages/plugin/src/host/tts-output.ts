import type { AnyVoiceEvent } from '@dsh-voice/protocol';

import type { Config } from './config.js';
import type { RuntimeManager } from './runtime-manager.js';
import { sanitizeForSpeech } from './sentence.js';
import { log, type HostContext } from './types.js';

export interface TtsStatus {
  readonly speaking: boolean;
  readonly utteranceId?: string;
  readonly lastText?: string;
}

/** Sends assistant sentences to the Runtime's single playback authority. */
export class TtsOutput {
  private readonly ctx: HostContext;
  private readonly manager: RuntimeManager;
  private readonly config: Config;
  private counter = 0;
  private current: string | null = null;
  private lastText = '';
  private readonly listeners = new Set<(status: TtsStatus) => void>();

  constructor(ctx: HostContext, manager: RuntimeManager, config: Config) {
    this.ctx = ctx;
    this.manager = manager;
    this.config = config;
  }

  get status(): TtsStatus {
    return {
      speaking: this.current !== null,
      utteranceId: this.current ?? undefined,
      lastText: this.lastText || undefined,
    };
  }

  onStatus(listener: (status: TtsStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  speak(text: string): boolean {
    if (!this.config.speakAssistant) return false;
    const clean = sanitizeForSpeech(text);
    if (!clean) return false;
    if (!this.manager.connected) {
      log(this.ctx, 'warn', 'runtime not connected; dropping speech', { chars: clean.length });
      return false;
    }
    this.counter += 1;
    const utteranceId = `voice-${Date.now()}-${this.counter}`;
    const accepted = this.manager.send('tts.speak', {
      utteranceId,
      text: clean.slice(0, 4000),
      interruptible: true,
    });
    if (accepted) {
      this.current = utteranceId;
      this.lastText = clean.slice(0, 200);
      this.emit();
    }
    return accepted;
  }

  cancel(reason: 'barge_in' | 'user_stop' | 'cancel' | 'error' = 'user_stop'): void {
    if (!this.manager.connected) return;
    this.manager.send('tts.cancel', {
      ...(this.current ? { utteranceId: this.current } : {}),
      reason,
    });
    this.current = null;
    this.emit();
  }

  handleRuntimeEvent(event: AnyVoiceEvent): void {
    if (event.type === 'tts.started') {
      this.current = String(event.payload.utteranceId ?? '');
      this.emit();
    } else if (event.type === 'tts.finished' || event.type === 'tts.interrupted') {
      if (String(event.payload.utteranceId ?? '') === this.current) {
        this.current = null;
        this.emit();
      }
    }
  }

  private emit(): void {
    const status = this.status;
    for (const listener of this.listeners) {
      try {
        listener(status);
      } catch {
        // Status consumers are advisory.
      }
    }
  }
}

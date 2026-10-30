import type { AnyVoiceEvent } from '@dsh-voice/protocol';

import type { AgentBridgeStatus, AgentState } from './agent-bridge.js';
import type { AvatarState, VoiceState } from './avatar-state.js';
import { deriveAvatarState, toPetWorkStatus } from './avatar-state.js';
import type { Config } from './config.js';
import type { DshAgentBridge } from './agent-bridge.js';
import type { TtsOutput, TtsStatus } from './tts-output.js';
import { log, type HostContext } from './types.js';

const PET_PREFIX = '/dsh-pet-7340';

export type PetConnection = 'disabled' | 'unavailable' | 'available';

export interface PetResult {
  readonly ok: boolean;
  readonly reason?: string;
  readonly message?: string;
  readonly playbackId?: string;
  readonly [key: string]: unknown;
}

export interface PetStatus {
  readonly connection: PetConnection;
  readonly baseUrl?: string;
  readonly petId: string;
  readonly locked: boolean;
  readonly lockExpiresAt?: number;
  readonly avatarState: AvatarState;
  readonly workStatus?: string;
  readonly lastError?: string;
  readonly ttsProvider: string;
}

export interface PetBridgeOptions {
  readonly fetch?: typeof fetch;
}

interface LockState {
  lockId: string;
  expiresAt: number;
}

function now(): number {
  return Date.now();
}

/**
 * HTTP bridge to the verified dsh-pet 0.3.8 API. It never imports dsh-pet
 * internals and never uses the pet as the main TTS playback path.
 */
export class PetBridge {
  private readonly ctx: HostContext;
  private readonly config: Config;
  private readonly bridge: DshAgentBridge;
  private readonly tts: TtsOutput;
  private readonly fetcher: typeof fetch;
  private readonly disposers: Array<() => void> = [];
  private connection: PetConnection = 'disabled';
  private lock: LockState | null = null;
  private lockTimer: NodeJS.Timeout | null = null;
  private probeTimer: NodeJS.Timeout | null = null;
  private releaseTimer: NodeJS.Timeout | null = null;
  private workStatus: string | null = null;
  private lastError: string | undefined;
  private voiceState: VoiceState = 'IDLE';
  private agentState: AgentState = 'IDLE';
  private ttsSpeaking = false;
  private avatar: AvatarState = 'idle';
  private stopped = false;

  constructor(
    ctx: HostContext,
    config: Config,
    bridge: DshAgentBridge,
    tts: TtsOutput,
    options: PetBridgeOptions = {},
  ) {
    this.ctx = ctx;
    this.config = config;
    this.bridge = bridge;
    this.tts = tts;
    this.fetcher = options.fetch ?? fetch;
    if (!config.petEnabled) {
      this.connection = 'disabled';
      return;
    }
    this.connection = 'unavailable';
    this.disposers.push(
      bridge.onStatus((status) => this.onAgentStatus(status)),
      tts.onStatus((status) => this.onTtsStatus(status)),
      tts.onText((text) => this.onSpeechText(text)),
    );
  }

  get status(): PetStatus {
    return {
      connection: this.connection,
      baseUrl: this.baseUrl() ?? undefined,
      petId: this.config.petId,
      locked: this.lock !== null && this.lock.expiresAt > now(),
      lockExpiresAt: this.lock?.expiresAt,
      avatarState: this.avatar,
      workStatus: this.workStatus ?? undefined,
      lastError: this.lastError,
      ttsProvider: this.config.petTtsProvider ? 'requested' : 'disabled',
    };
  }

  async start(): Promise<void> {
    if (!this.config.petEnabled) return;
    await this.probe();
  }

  async stop(): Promise<void> {
    this.stopped = true;
    if (this.probeTimer) {
      clearTimeout(this.probeTimer);
      this.probeTimer = null;
    }
    if (this.releaseTimer) {
      clearTimeout(this.releaseTimer);
      this.releaseTimer = null;
    }
    for (const dispose of this.disposers.splice(0)) dispose();
    await this.releaseLock();
    if (this.workStatus !== null) {
      await this.clearWorkStatus();
    }
  }

  handleRuntimeEvent(event: AnyVoiceEvent): void {
    if (event.type !== 'session.state_changed') return;
    const value = String(event.payload.voiceState ?? '');
    if (!value) return;
    this.voiceState = value as VoiceState;
    this.applyAvatar();
  }

  async getState(): Promise<PetResult> {
    return this.request('GET', '/state');
  }

  async refresh(): Promise<PetResult> {
    const state = await this.getState();
    if (state.ok) this.markAvailable();
    return state;
  }

  async setWorkStatus(state: string, task?: string): Promise<PetResult> {
    const result = await this.request('POST', '/work-status', {
      state,
      ...(task ? { task: task.slice(0, 40) } : {}),
    });
    if (result.ok) this.workStatus = state;
    return result;
  }

  async clearWorkStatus(): Promise<PetResult> {
    const result = await this.request('DELETE', '/work-status');
    if (result.ok) this.workStatus = null;
    return result;
  }

  async broadcast(
    text: string,
    options: { duration?: number; anim?: boolean; image?: string; url?: string } = {},
  ): Promise<PetResult> {
    const clean = text.trim();
    if (!clean) return { ok: false, reason: 'empty-text' };
    return this.withLock((lock) =>
      this.request(
        'POST',
        '/broadcast',
        {
          text: clean.slice(0, 4_000),
          duration: options.duration ?? 10_000,
          anim: options.anim ?? true,
          ...(options.image ? { image: options.image } : {}),
          ...(options.url ? { url: options.url } : {}),
        },
        { lock },
      ),
    );
  }

  async clearBubble(): Promise<PetResult> {
    return this.withLock((lock) => this.request('POST', '/bubble/clear', undefined, { lock }));
  }

  async playAnimation(animation: {
    name?: string;
    url?: string;
    facing?: 'left' | 'right';
  }): Promise<PetResult> {
    if (!animation.name && !animation.url) {
      return { ok: false, reason: 'bad-request', message: 'name or url is required' };
    }
    return this.withLock((lock) =>
      this.request(
        'POST',
        '/anim',
        {
          ...(animation.name ? { name: animation.name } : {}),
          ...(animation.url ? { url: animation.url } : {}),
          ...(animation.facing ? { facing: animation.facing } : {}),
        },
        { lock },
      ),
    );
  }

  async wake(): Promise<PetResult> {
    return this.withLock((lock) => this.request('POST', '/wake', undefined, { lock }));
  }

  async sleep(): Promise<PetResult> {
    return this.withLock((lock) => this.request('POST', '/sleep', undefined, { lock }));
  }

  async acquireLock(ttl = this.config.petLockTtlMs): Promise<boolean> {
    if (this.connection !== 'available') return false;
    const result = await this.request('POST', '/lock', { ttl });
    const lockId = typeof result.lockId === 'string' ? result.lockId : '';
    const expiresAt = typeof result.expiresAt === 'number' ? result.expiresAt : now() + ttl;
    if (!result.ok || !lockId) {
      this.lastError = result.message ?? result.reason ?? 'lock failed';
      return false;
    }
    this.lock = { lockId, expiresAt };
    this.startLockRenewal();
    return true;
  }

  async renewLock(): Promise<boolean> {
    if (!this.lock) return false;
    const result = await this.request('POST', '/lock', {
      lockId: this.lock.lockId,
      ttl: this.config.petLockTtlMs,
    });
    if (!result.ok) {
      this.lock = null;
      this.stopLockRenewal();
      this.lastError = result.message ?? result.reason ?? 'lock renewal failed';
      return false;
    }
    this.lock.expiresAt =
      typeof result.expiresAt === 'number' ? result.expiresAt : now() + this.config.petLockTtlMs;
    return true;
  }

  async releaseLock(): Promise<void> {
    this.stopLockRenewal();
    const lock = this.lock;
    this.lock = null;
    if (!lock) return;
    await this.request('POST', '/lock/release', { lockId: lock.lockId });
  }

  private async withLock(action: (lockId: string) => Promise<PetResult>): Promise<PetResult> {
    if (this.connection !== 'available') {
      return { ok: false, reason: 'unavailable', message: 'dsh-pet is not reachable' };
    }
    if (!(await this.ensureLock())) {
      return {
        ok: false,
        reason: 'locked',
        message: this.lastError ?? 'could not acquire pet lock',
      };
    }
    let result = await action(this.lock?.lockId ?? '');
    if (
      !result.ok &&
      (result.reason === 'lock-required' || result.reason === 'lock-lost') &&
      this.lock
    ) {
      this.lock = null;
      this.stopLockRenewal();
      if (await this.ensureLock()) {
        const refreshed = this.lock as LockState | null;
        result = await action(refreshed?.lockId ?? '');
      }
    }
    return result;
  }

  private async ensureLock(): Promise<boolean> {
    if (this.lock && this.lock.expiresAt > now() + 2_000) return true;
    this.lock = null;
    this.stopLockRenewal();
    return this.acquireLock();
  }

  private startLockRenewal(): void {
    this.stopLockRenewal();
    const interval = Math.max(5_000, Math.floor(this.config.petLockTtlMs / 2));
    this.lockTimer = setInterval(() => {
      void this.renewLock().then((ok) => {
        if (!ok) log(this.ctx, 'warn', 'dsh-pet lock renewal failed');
      });
    }, interval);
    this.lockTimer.unref?.();
  }

  private stopLockRenewal(): void {
    if (this.lockTimer) {
      clearInterval(this.lockTimer);
      this.lockTimer = null;
    }
  }

  private onAgentStatus(status: AgentBridgeStatus): void {
    this.agentState = status.agentState;
    this.applyAvatar();
  }

  private onTtsStatus(status: TtsStatus): void {
    this.ttsSpeaking = status.speaking;
    if (
      !status.speaking &&
      (this.agentState === 'IDLE' ||
        this.agentState === 'SUCCESS' ||
        this.agentState === 'ERROR' ||
        this.agentState === 'CANCELLED')
    ) {
      this.scheduleRelease(2_000);
    }
    this.applyAvatar();
  }

  private onSpeechText(text: string): void {
    if (!this.config.petBubbleEnabled || this.connection !== 'available') return;
    const duration = Math.min(30_000, Math.max(3_000, text.length * 180));
    void this.broadcast(text, { duration, anim: true }).then((result) => {
      if (!result.ok) log(this.ctx, 'warn', 'dsh-pet bubble rejected', { reason: result.reason });
    });
  }

  private scheduleRelease(delayMs: number): void {
    if (this.releaseTimer) clearTimeout(this.releaseTimer);
    this.releaseTimer = setTimeout(() => {
      this.releaseTimer = null;
      void this.releaseLock();
    }, delayMs);
    this.releaseTimer.unref?.();
  }

  private applyAvatar(): void {
    const next = deriveAvatarState({
      voiceState: this.voiceState,
      agentState: this.agentState,
      ttsSpeaking: this.ttsSpeaking,
    });
    if (next === this.avatar) return;
    this.avatar = next;
    if (!this.config.petUseWorkStatus || this.connection !== 'available') return;
    const mapped = toPetWorkStatus(next);
    if (mapped) {
      void this.setWorkStatus(mapped, this.agentToolName());
    } else if (this.workStatus !== null) {
      void this.clearWorkStatus();
    }
  }

  private agentToolName(): string | undefined {
    const tool = this.bridge.status.toolName;
    return tool ? tool.slice(0, 40) : undefined;
  }

  private async probe(): Promise<void> {
    if (this.stopped || !this.config.petEnabled) return;
    const base = this.baseUrl();
    if (!base) {
      this.scheduleProbe();
      return;
    }
    try {
      const response = await this.fetcher(`${base}${PET_PREFIX}/state`, {
        signal: AbortSignal.timeout(Math.min(this.config.petBridgeTimeoutMs, 2_000)),
      });
      if (response.ok) {
        const value = (await response.json()) as { pets?: unknown; sections?: unknown };
        if (value && typeof value === 'object' && ('pets' in value || 'sections' in value)) {
          this.markAvailable();
          return;
        }
      }
      this.markUnavailable(`state HTTP ${response.status}`);
      this.scheduleProbe();
    } catch (error) {
      this.markUnavailable(error instanceof Error ? error.message : String(error));
      this.scheduleProbe();
    }
  }

  private scheduleProbe(): void {
    if (this.stopped || this.probeTimer) return;
    this.probeTimer = setTimeout(() => {
      this.probeTimer = null;
      void this.probe();
    }, 5_000);
    this.probeTimer.unref?.();
  }

  private markAvailable(): void {
    if (this.connection !== 'available') log(this.ctx, 'info', 'dsh-pet bridge available');
    this.connection = 'available';
    this.lastError = undefined;
  }

  private markUnavailable(reason: string): void {
    if (this.connection === 'available')
      log(this.ctx, 'warn', 'dsh-pet bridge unavailable', { reason });
    this.connection = 'unavailable';
    this.lastError = reason;
  }

  private async request(
    method: string,
    path: string,
    body?: unknown,
    options: { lock?: string } = {},
  ): Promise<PetResult> {
    const base = this.baseUrl();
    if (!base)
      return { ok: false, reason: 'unavailable', message: 'DSH webServer is not available' };
    let url: URL;
    try {
      url = new URL(`${base}${PET_PREFIX}${path}`);
    } catch {
      return { ok: false, reason: 'bad-base-url', message: base };
    }
    url.searchParams.set('pet', this.config.petId);
    if (options.lock) url.searchParams.set('lock', options.lock);
    try {
      const response = await this.fetcher(url, {
        method,
        headers: body === undefined ? undefined : { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(this.config.petBridgeTimeoutMs),
      });
      const text = await response.text();
      let value: Record<string, unknown> = {};
      if (text) {
        try {
          value = JSON.parse(text) as Record<string, unknown>;
        } catch {
          return { ok: false, reason: 'invalid-response', message: text.slice(0, 200) };
        }
      }
      if (!response.ok) {
        return {
          ok: false,
          reason: `http-${response.status}`,
          message: typeof value.message === 'string' ? value.message : undefined,
        };
      }
      if (value.ok === false) {
        return {
          ok: false,
          reason: typeof value.reason === 'string' ? value.reason : 'failed',
          message: typeof value.message === 'string' ? value.message : undefined,
          ...value,
        };
      }
      if (this.connection !== 'available') this.markAvailable();
      return { ok: true, ...value };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.markUnavailable(message);
      return { ok: false, reason: 'unavailable', message };
    }
  }

  private baseUrl(): string | null {
    if (this.config.petBaseUrl) return this.config.petBaseUrl.replace(/\/+$/, '');
    const server = this.ctx.webServer ?? this.ctx.get<{ port?: number }>('webServer', false);
    const port = (server as { port?: number } | undefined)?.port ?? 0;
    return port > 0 ? `http://127.0.0.1:${port}` : null;
  }
}

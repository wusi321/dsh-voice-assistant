import type { ChildProcess } from 'node:child_process';
import { spawn as nodeSpawn } from 'node:child_process';

import type { AnyVoiceEvent } from '@dsh-voice/protocol';

import type { Config } from './config.js';
import {
  discoveryPathFor,
  isProcessAlive,
  readDiscovery,
  waitForDiscovery,
  type DiscoveryInfo,
} from './discovery.js';
import { RuntimeClient, type RuntimeClientOptions, type RuntimeConnectionState } from './runtime-client.js';
import { log, type HostContext } from './types.js';

export type RuntimeState = 'stopped' | 'starting' | 'connected' | 'error';

export interface RuntimeStatus {
  readonly state: RuntimeState;
  readonly detail?: string;
  readonly port?: number;
  readonly pid?: number;
  readonly runtimeVersion?: string;
  readonly discoveryPath: string;
}

export interface RuntimeManagerDeps {
  readonly spawn?: typeof nodeSpawn;
  readonly readDiscovery?: typeof readDiscovery;
  readonly waitForDiscovery?: typeof waitForDiscovery;
  readonly connect?: (
    info: DiscoveryInfo,
    options: RuntimeClientOptions,
  ) => Promise<RuntimeClient>;
  readonly isProcessAlive?: (pid: number) => boolean;
}

/** Spawns or attaches to the Python Runtime and keeps one authenticated client. */
export class RuntimeManager {
  private readonly ctx: HostContext;
  private readonly config: Config;
  private readonly deps: Required<RuntimeManagerDeps>;
  private readonly path: string;
  private client: RuntimeClient | null = null;
  private child: ChildProcess | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private attempt = 0;
  private running = false;
  private statusValue: RuntimeStatus;

  constructor(ctx: HostContext, config: Config, deps: RuntimeManagerDeps = {}) {
    this.ctx = ctx;
    this.config = config;
    this.path = config.discoveryPath || discoveryPathFor();
    this.deps = {
      spawn: deps.spawn ?? nodeSpawn,
      readDiscovery: deps.readDiscovery ?? readDiscovery,
      waitForDiscovery: deps.waitForDiscovery ?? waitForDiscovery,
      connect:
        deps.connect ??
        (async (info, options) => {
          const client = new RuntimeClient(options);
          await client.connect(info);
          return client;
        }),
      isProcessAlive: deps.isProcessAlive ?? isProcessAlive,
    };
    this.statusValue = { state: 'stopped', discoveryPath: this.path };
  }

  get discoveryPath(): string {
    return this.path;
  }

  get status(): RuntimeStatus {
    return this.statusValue;
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    await this.establish();
  }

  stop(): void {
    this.running = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.client?.close();
    this.client = null;
    if (this.child && !this.child.killed) {
      this.child.kill();
    }
    this.child = null;
    this.setStatus({ state: 'stopped', discoveryPath: this.path });
  }

  async refresh(): Promise<void> {
    if (!this.running) {
      await this.start();
      return;
    }
    this.client?.close();
    this.client = null;
    await this.establish();
  }

  private async establish(): Promise<void> {
    if (!this.running) return;
    this.setStatus({ state: 'starting', discoveryPath: this.path });
    try {
      let info = await this.deps.readDiscovery(this.path);
      if (info && !this.deps.isProcessAlive(info.pid)) info = null;
      if (!info && this.config.autoStart) {
        this.spawnRuntime();
        info = await this.deps.waitForDiscovery(this.path, this.config.startupTimeoutMs);
      }
      if (!info) {
        throw new Error(`runtime discovery not found: ${this.path}`);
      }
      const client = await this.deps.connect(info, {
        onEvent: (event: AnyVoiceEvent) => this.handleEvent(event),
        onState: (state, detail) => this.handleClientState(state, detail),
      });
      this.client = client;
      this.attempt = 0;
      this.setStatus({
        state: 'connected',
        port: info.port,
        pid: info.pid,
        runtimeVersion: info.runtimeVersion,
        discoveryPath: this.path,
      });
      log(this.ctx, 'info', 'runtime connected', { port: info.port });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.setStatus({ state: 'error', detail: message, discoveryPath: this.path });
      log(this.ctx, 'warn', 'runtime connection failed', { error: message });
      this.scheduleReconnect();
    }
  }

  private spawnRuntime(): void {
    if (this.child) return;
    const args = ['daemon'];
    if (this.config.fakeAudio) args.push('--fake-audio');
    try {
      this.child = this.deps.spawn(this.config.runtimeCommand, args, {
        stdio: 'ignore',
        windowsHide: true,
      });
      this.child.once('exit', () => {
        this.child = null;
      });
      this.child.once('error', (error) => {
        log(this.ctx, 'error', 'runtime spawn failed', { error: String(error) });
      });
      log(this.ctx, 'info', 'runtime spawned', { command: this.config.runtimeCommand });
    } catch (error) {
      log(this.ctx, 'error', 'runtime spawn threw', { error: String(error) });
    }
  }

  private handleEvent(event: AnyVoiceEvent): void {
    if (event.type === 'runtime.error') {
      log(this.ctx, 'warn', 'runtime error event', { event: event.payload });
    }
  }

  private handleClientState(state: RuntimeConnectionState, detail?: string): void {
    if (state === 'closed' && this.running) {
      this.setStatus({ state: 'stopped', detail, discoveryPath: this.path });
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (!this.running || this.reconnectTimer) return;
    const delay = Math.min(
      this.config.reconnectMaxMs,
      this.config.reconnectMinMs * 2 ** this.attempt,
    );
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.establish();
    }, delay);
    this.reconnectTimer.unref?.();
  }

  private setStatus(status: RuntimeStatus): void {
    this.statusValue = status;
  }
}

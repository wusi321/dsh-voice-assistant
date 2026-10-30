import { randomUUID } from 'node:crypto';
import WebSocket from 'ws';

import type { AnyVoiceEvent, VoiceEventType } from '@dsh-voice/protocol';
import { PROTOCOL_VERSION } from '@dsh-voice/protocol';
import type { DiscoveryInfo } from './discovery.js';

export type RuntimeConnectionState = 'idle' | 'connecting' | 'ready' | 'closed' | 'error';

export interface RuntimeClientOptions {
  readonly connectTimeoutMs?: number;
  readonly heartbeatIntervalMs?: number;
  readonly heartbeatTimeoutMs?: number;
  readonly onEvent?: (event: AnyVoiceEvent) => void;
  readonly onState?: (state: RuntimeConnectionState, detail?: string) => void;
}

/** Authenticated WebSocket client for one Runtime discovery record. */
export class RuntimeClient {
  private socket: WebSocket | null = null;
  private stateValue: RuntimeConnectionState = 'idle';
  private sequence = 0;
  private readonly sessionId = 'runtime';
  private readonly connectTimeoutMs: number;
  private readonly heartbeatIntervalMs: number;
  private readonly heartbeatTimeoutMs: number;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private pendingPing: { pingId: string; timer: NodeJS.Timeout } | null = null;
  private readonly onEvent?: (event: AnyVoiceEvent) => void;
  private readonly onState?: (state: RuntimeConnectionState, detail?: string) => void;

  constructor(options: RuntimeClientOptions = {}) {
    this.connectTimeoutMs = options.connectTimeoutMs ?? 5_000;
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 10_000;
    this.heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? 5_000;
    this.onEvent = options.onEvent;
    this.onState = options.onState;
  }

  get state(): RuntimeConnectionState {
    return this.stateValue;
  }

  async connect(info: DiscoveryInfo): Promise<void> {
    if (this.socket) throw new Error('runtime client is already connected');
    this.setState('connecting');
    const socket = new WebSocket(`ws://${info.host}:${info.port}`);
    this.socket = socket;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error('runtime handshake timed out'));
        socket.close();
      }, this.connectTimeoutMs);
      timer.unref?.();

      const fail = (error: Error): void => {
        clearTimeout(timer);
        this.setState('error', error.message);
        reject(error);
      };

      socket.on('open', () => {
        socket.send(
          JSON.stringify({
            type: 'auth',
            version: 1,
            token: info.token,
            clientId: 'dsh-voice-assistant',
            protocolVersion: PROTOCOL_VERSION,
          }),
        );
      });

      socket.on('message', (raw) => {
        let message: unknown;
        try {
          message = JSON.parse(raw.toString());
        } catch {
          return;
        }
        if (!message || typeof message !== 'object') return;
        const record = message as {
          type?: unknown;
          code?: unknown;
          message?: unknown;
          payload?: { pingId?: unknown };
        };
        if (record.type === 'auth.error') {
          fail(new Error(String(record.message ?? record.code ?? 'authentication failed')));
          return;
        }
        if (record.type === 'auth.ok') return;
        if (record.type === 'runtime.ready') {
          clearTimeout(timer);
          this.setState('ready');
          this.emit(message as AnyVoiceEvent);
          this.startHeartbeat();
          resolve();
          return;
        }
        if (record.type === 'pong') {
          const pingId = String(record.payload?.pingId ?? '');
          if (this.pendingPing?.pingId === pingId) {
            clearTimeout(this.pendingPing.timer);
            this.pendingPing = null;
          }
        }
        this.emit(message as AnyVoiceEvent);
      });

      socket.on('error', (error) =>
        fail(error instanceof Error ? error : new Error(String(error))),
      );
      socket.on('close', () => {
        this.stopHeartbeat();
        if (this.stateValue !== 'ready') {
          clearTimeout(timer);
          reject(new Error('runtime connection closed before ready'));
        }
        this.setState('closed');
      });
    });
  }

  send(type: VoiceEventType, payload: Record<string, unknown>): boolean {
    if (this.stateValue !== 'ready' || !this.socket) return false;
    this.sequence += 1;
    const event = {
      version: 1,
      id: randomUUID(),
      sessionId: this.sessionId,
      sequence: this.sequence,
      timestamp: Date.now(),
      type,
      payload,
    };
    this.socket.send(JSON.stringify(event));
    return true;
  }

  close(): void {
    this.stopHeartbeat();
    if (!this.socket) return;
    this.socket.removeAllListeners();
    this.socket.close();
    this.socket = null;
    this.setState('closed');
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.pendingPing) return;
      const pingId = randomUUID();
      if (!this.send('ping', { pingId })) return;
      const timer = setTimeout(() => {
        this.pendingPing = null;
        this.socket?.close(4002, 'heartbeat timeout');
      }, this.heartbeatTimeoutMs);
      timer.unref?.();
      this.pendingPing = { pingId, timer };
    }, this.heartbeatIntervalMs);
    this.heartbeatTimer.unref?.();
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.pendingPing) {
      clearTimeout(this.pendingPing.timer);
      this.pendingPing = null;
    }
  }

  private emit(event: AnyVoiceEvent): void {
    try {
      this.onEvent?.(event);
    } catch {
      // A consumer error must not tear down the transport.
    }
  }

  private setState(state: RuntimeConnectionState, detail?: string): void {
    this.stateValue = state;
    this.onState?.(state, detail);
  }
}

import { randomUUID } from 'node:crypto';

import type { AnyVoiceEvent } from '@dsh-voice/protocol';

import type { Config } from './config.js';
import type {
  AssistantFrame,
  AssistantStreamPayload,
  DshAgent,
  DshSessionRef,
  SessionEvent,
} from './dsh-types.js';
import type { SessionBinder } from './session-binder.js';
import { SentenceSegmenter } from './sentence.js';
import type { TtsOutput } from './tts-output.js';
import { log, type HostContext } from './types.js';

export type AgentState =
  | 'IDLE'
  | 'THINKING'
  | 'TOOL_CALLING'
  | 'TOOL_RUNNING'
  | 'WAITING_CONFIRMATION'
  | 'SUCCESS'
  | 'ERROR'
  | 'CANCELLED';

export interface AgentBridgeStatus {
  readonly sessionId: string | null;
  readonly agentStatus?: string;
  readonly agentState: AgentState;
  readonly toolName?: string;
  readonly lastText?: string;
  readonly lastError?: string;
}

function userMessage(text: string): Record<string, unknown> {
  // 0.2.1's MessageSourceMap has `user`; using it is stable and does not
  // impersonate a plugin-owned context message.
  return {
    id: randomUUID(),
    role: 'user',
    content: [{ type: 'text', text }],
    source: { kind: 'user' },
  };
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T | 'timeout'> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<'timeout'>((resolve) => {
    timer = setTimeout(() => resolve('timeout'), timeoutMs);
    timer.unref?.();
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/**
 * Maps the voice session to the verified DSH 0.2.1 Agent API.
 * It never creates an Agent and never bypasses DSH permissions.
 */
export class DshAgentBridge {
  private readonly ctx: HostContext;
  private readonly config: Config;
  private readonly binder: SessionBinder;
  private readonly tts: TtsOutput;
  private segmenter = new SentenceSegmenter();
  private state: AgentState = 'IDLE';
  private toolName: string | undefined;
  private lastText = '';
  private lastError: string | undefined;
  private readonly listeners = new Set<(status: AgentBridgeStatus) => void>();

  constructor(ctx: HostContext, binder: SessionBinder, tts: TtsOutput, config: Config) {
    this.ctx = ctx;
    this.binder = binder;
    this.tts = tts;
    this.config = config;
  }

  get status(): AgentBridgeStatus {
    return {
      sessionId: this.binder.status().sessionId,
      agentStatus: this.binder.status().agentStatus,
      agentState: this.state,
      toolName: this.toolName,
      lastText: this.lastText || undefined,
      lastError: this.lastError,
    };
  }

  onStatus(listener: (status: AgentBridgeStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  sendMessage(text: string): string {
    const clean = text.trim();
    if (!clean) throw new Error('empty voice message');
    const agent = this.binder.resolve();
    if (!agent) throw new Error('no live DSH session is bound');
    agent.followup(userMessage(clean));
    this.lastText = clean;
    this.setState('THINKING');
    return agent.id;
  }

  steerMessage(text: string): string {
    const clean = text.trim();
    if (!clean) throw new Error('empty steer message');
    const agent = this.binder.resolve();
    if (!agent) throw new Error('no live DSH session is bound');
    agent.steer(userMessage(clean));
    this.lastText = clean;
    return agent.id;
  }

  async cancelCurrentTurn(): Promise<'idle' | 'cancelled' | 'timeout'> {
    const agent = this.binder.resolve();
    if (!agent) return 'idle';
    if (agent.status === 'idle') return 'idle';
    agent.cancel({ kind: 'user' }, { keepInbox: true });
    const outcome = await withTimeout(agent.whenIdle(), this.config.cancelTimeoutMs);
    if (outcome === 'timeout') {
      this.lastError = 'agent did not settle before cancel timeout';
      this.setState('ERROR');
      return 'timeout';
    }
    this.setState('CANCELLED');
    return 'cancelled';
  }

  handleRuntimeEvent(event: AnyVoiceEvent): void {
    if (event.type === 'speech.final') {
      const text = String(event.payload.text ?? '').trim();
      if (!text) return;
      try {
        this.sendMessage(text);
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : String(error);
        log(this.ctx, 'warn', 'voice message rejected', { error: this.lastError });
        this.emit();
      }
      return;
    }
    if (event.type === 'session.interrupt') {
      const action = String(event.payload.action ?? '');
      if (action === 'tts') {
        this.tts.cancel('user_stop');
      } else if (action === 'agent') {
        void this.cancelCurrentTurn();
      } else if (action === 'steer') {
        const text = String(event.payload.text ?? '').trim();
        if (text) {
          try {
            this.steerMessage(text);
          } catch (error) {
            this.lastError = error instanceof Error ? error.message : String(error);
            this.emit();
          }
        }
      }
    }
  }

  subscribe(): () => void {
    const offStream = this.ctx.on('agent/assistant-stream', (payload: AssistantStreamPayload) => {
      this.onAssistantStream(payload);
    });
    const offSession = this.ctx.on(
      'session/event',
      (session: DshSessionRef, event: SessionEvent) => {
        this.onSessionEvent(session, event);
      },
    );
    const offError = this.ctx.on('agent/error', (payload: { agent?: DshAgent }) => {
      if (!payload?.agent) return;
      if (payload.agent.id !== this.binder.status().sessionId) return;
      this.lastError = 'agent error';
      this.setState('ERROR');
    });
    return () => {
      offStream();
      offSession();
      offError();
    };
  }

  private onAssistantStream(payload: AssistantStreamPayload): void {
    const bound = this.binder.status().sessionId;
    if (!bound || payload.agent.id !== bound) return;
    const frame: AssistantFrame = payload.frame;
    if (frame.type === 'start') {
      this.segmenter.reset();
      this.setState('THINKING');
      return;
    }
    if (frame.type === 'chunk') {
      if (frame.chunk?.type !== 'text-delta') return; // never speak reasoning/tool args
      const sentences = this.segmenter.push(String(frame.chunk.text ?? ''));
      for (const sentence of sentences) this.tts.speak(sentence);
      return;
    }
    if (frame.type === 'end') {
      for (const sentence of this.segmenter.flush()) this.tts.speak(sentence);
      if (this.state === 'THINKING') this.setState('IDLE');
    }
  }

  private onSessionEvent(session: DshSessionRef, event: SessionEvent): void {
    const bound = this.binder.status().sessionId;
    if (!bound || session.id !== bound) return;
    const type = event.type ?? '';
    if (type === 'turn/start') {
      this.setState('THINKING');
    } else if (type === 'tool/call') {
      this.toolName = typeof event.data?.name === 'string' ? event.data.name : undefined;
      this.setState('TOOL_RUNNING');
    } else if (type === 'tool/result') {
      this.setState('THINKING');
    } else if (type === 'approval/asked') {
      this.setState('WAITING_CONFIRMATION');
    } else if (type === 'turn/end') {
      const reason = String(event.data?.reason?.kind ?? '');
      this.toolName = undefined;
      if (reason === 'completed') this.setState('SUCCESS');
      else if (reason === 'aborted') this.setState('CANCELLED');
      else if (reason === 'error' || reason === 'max-tokens') this.setState('ERROR');
      else if (reason === 'blocked') this.setState('WAITING_CONFIRMATION');
      else this.setState('IDLE');
    }
  }

  private setState(state: AgentState): void {
    this.state = state;
    this.emit();
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

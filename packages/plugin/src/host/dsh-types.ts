/** Minimal structural types for the DSH 0.2.1-rc.3 Agent/Session surface. */

export type AgentStatus = 'idle' | 'running';

export interface DshAgent {
  readonly id: string;
  readonly status: AgentStatus;
  readonly session: { readonly id: string };
  followup(message: unknown): void;
  steer(message: unknown): void;
  cancel(cause: { kind: 'user' }, options?: { keepInbox?: boolean }): void;
  whenIdle(): Promise<void>;
}

export interface DshAgentService {
  get(id: string): DshAgent | undefined;
  list(): DshAgent[];
  roots(): DshAgent[];
}

export interface AssistantFrameChunk {
  readonly type: string;
  readonly text?: string;
  readonly blockType?: string;
  readonly block?: { readonly type?: string; readonly text?: string };
}

export interface AssistantFrame {
  readonly type: 'start' | 'chunk' | 'end';
  readonly attemptId?: string;
  readonly revision?: number;
  readonly turn?: number;
  readonly step?: number;
  readonly chunk?: AssistantFrameChunk;
  readonly index?: number;
  readonly outcome?: { readonly kind?: string };
}

export interface AssistantStreamPayload {
  readonly agent: DshAgent;
  readonly frame: AssistantFrame;
}

export interface SessionEventData {
  readonly reason?: { readonly kind?: string };
  readonly name?: string;
  readonly callId?: string;
  readonly [key: string]: unknown;
}

export interface SessionEvent {
  readonly type?: string;
  readonly data?: SessionEventData;
}

export interface DshSessionRef {
  readonly id: string;
}

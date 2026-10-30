import type { Config } from './config.js';
import type { DshAgent, DshAgentService } from './dsh-types.js';
import type { HostContext } from './types.js';

export type SessionSource = 'client' | 'fixed' | 'last' | 'none';

export interface BoundSessionStatus {
  readonly sessionId: string | null;
  readonly live: boolean;
  readonly source: SessionSource;
  readonly agentStatus?: string;
}

/** Owns the "which DSH Session does voice target" decision. */
export class SessionBinder {
  private readonly ctx: HostContext;
  private readonly config: Config;
  private activeId: string | null = null;
  private activeSource: SessionSource = 'none';
  private readonly listeners = new Set<(status: BoundSessionStatus) => void>();

  constructor(ctx: HostContext, config: Config) {
    this.ctx = ctx;
    this.config = config;
  }

  get activeSessionId(): string | null {
    return this.activeId;
  }

  setActive(sessionId: string, source: SessionSource = 'client'): BoundSessionStatus {
    const id = sessionId.trim();
    if (!id) throw new Error('sessionId must be non-empty');
    this.activeId = id;
    this.activeSource = source;
    const status = this.status();
    this.notify(status);
    return status;
  }

  resolve(): DshAgent | undefined {
    const agents = this.agents();
    if (!agents) return undefined;
    if (this.config.sessionStrategy === 'fixed') {
      const id = this.config.fixedSessionId.trim();
      return id ? agents.get(id) : undefined;
    }
    if (this.config.sessionStrategy === 'active' && this.activeId) {
      return agents.get(this.activeId);
    }
    const roots = agents.roots();
    if (roots.length > 0) {
      this.activeSource = 'last';
      return roots[roots.length - 1];
    }
    const all = agents.list();
    if (all.length > 0) {
      this.activeSource = 'last';
      return all[all.length - 1];
    }
    return undefined;
  }

  status(): BoundSessionStatus {
    const agents = this.agents();
    if (this.config.sessionStrategy === 'fixed') {
      const id = this.config.fixedSessionId.trim() || null;
      const agent = id && agents ? agents.get(id) : undefined;
      return {
        sessionId: id,
        live: Boolean(agent),
        source: id ? 'fixed' : 'none',
        agentStatus: agent?.status,
      };
    }
    if (this.config.sessionStrategy === 'active' && this.activeId) {
      const agent = agents?.get(this.activeId);
      return {
        sessionId: this.activeId,
        live: Boolean(agent),
        source: 'client',
        agentStatus: agent?.status,
      };
    }
    const agent = this.resolve();
    return {
      sessionId: agent?.id ?? null,
      live: Boolean(agent),
      source: agent ? 'last' : 'none',
      agentStatus: agent?.status,
    };
  }

  subscribe(listener: (status: BoundSessionStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(status: BoundSessionStatus): void {
    for (const listener of this.listeners) {
      try {
        listener(status);
      } catch {
        // A UI/status listener must not break voice routing.
      }
    }
  }

  private agents(): DshAgentService | undefined {
    return this.ctx.agents ?? this.ctx.get<DshAgentService>('agents', false);
  }
}

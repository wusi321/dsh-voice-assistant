/** Minimal structural types for the DSH Cordis Host context used by this plugin. */
import type { IncomingMessage, ServerResponse } from 'node:http';

export interface HostLogger {
  info(message: string, context?: unknown): void;
  warn(message: string, context?: unknown): void;
  error(message: string, context?: unknown): void;
}

export interface WebServerRoute {
  kind: 'prefix';
  path: string;
  handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>;
}

export interface WebServer {
  register(route: WebServerRoute): () => void;
}

export interface HostContext {
  effect(register: () => void | (() => void), label?: string): () => void;
  on(event: string, handler: (...args: any[]) => void): () => void;
  get<T = any>(name: string, required?: boolean): T | undefined;
  logger?: HostLogger;
  webServer?: WebServer;
}

export function log(
  ctx: HostContext,
  level: 'info' | 'warn' | 'error',
  message: string,
  context?: unknown,
): void {
  const logger = ctx.logger;
  if (logger) {
    logger[level](message, context);
    return;
  }
  const line = `[voice-assistant] ${message}`;
  if (level === 'error') console.error(line, context ?? '');
  else if (level === 'warn') console.warn(line, context ?? '');
  else console.info(line, context ?? '');
}

import type { IncomingMessage, ServerResponse } from 'node:http';

import type { AgentBridgeStatus, DshAgentBridge } from './agent-bridge.js';
import type { BoundSessionStatus, SessionBinder } from './session-binder.js';
import type { RuntimeManager, RuntimeStatus } from './runtime-manager.js';
import type { TtsOutput, TtsStatus } from './tts-output.js';
import type { HostContext, WebServer } from './types.js';

const ROUTE_PREFIX = '/dsh-voice-assistant';
const MAX_BODY_BYTES = 8 * 1024;

function sendJson(res: ServerResponse, status: number, value: unknown): void {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function statusPayload(
  runtime: RuntimeStatus,
  session: BoundSessionStatus,
  agent: AgentBridgeStatus,
  tts: TtsStatus,
): Record<string, unknown> {
  return {
    state: runtime.state,
    detail: runtime.detail,
    port: runtime.port,
    pid: runtime.pid,
    runtimeVersion: runtime.runtimeVersion,
    discoveryPath: runtime.discoveryPath,
    session,
    agent,
    tts,
  };
}

async function readJsonBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error('body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        reject(new Error('invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

/**
 * Read-only status plus one narrow write: the Client reports which session the
 * user is looking at. No Agent/TTS command is exposed over HTTP.
 */
export function registerStatusRoute(
  ctx: HostContext,
  manager: RuntimeManager,
  binder: SessionBinder,
  bridge: DshAgentBridge,
  tts: TtsOutput,
  enabled: boolean,
): () => void {
  const webServer: WebServer | undefined = ctx.webServer ?? ctx.get<WebServer>('webServer', false);
  if (!enabled || !webServer) return () => {};

  return webServer.register({
    kind: 'prefix',
    path: ROUTE_PREFIX,
    handler: async (req: IncomingMessage, res: ServerResponse) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1');
      if (req.method === 'GET' && url.pathname === `${ROUTE_PREFIX}/status`) {
        sendJson(
          res,
          200,
          statusPayload(manager.status, binder.status(), bridge.status, tts.status),
        );
        return;
      }
      if (req.method === 'POST' && url.pathname === `${ROUTE_PREFIX}/active-session`) {
        try {
          const body = (await readJsonBody(req)) as { sessionId?: unknown };
          const sessionId = typeof body.sessionId === 'string' ? body.sessionId : '';
          if (!sessionId.trim()) {
            sendJson(res, 400, { error: 'sessionId_required' });
            return;
          }
          sendJson(res, 200, { ok: true, session: binder.setActive(sessionId) });
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : 'invalid_request',
          });
        }
        return;
      }
      sendJson(res, 404, { error: 'not_found' });
    },
  });
}

import type { IncomingMessage, ServerResponse } from 'node:http';

import type { RuntimeManager, RuntimeStatus } from './runtime-manager.js';
import type { HostContext, WebServer } from './types.js';

const ROUTE_PREFIX = '/dsh-voice-assistant';

function sendJson(res: ServerResponse, status: number, value: unknown): void {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function statusPayload(status: RuntimeStatus): Record<string, unknown> {
  return {
    state: status.state,
    detail: status.detail,
    port: status.port,
    pid: status.pid,
    runtimeVersion: status.runtimeVersion,
    discoveryPath: status.discoveryPath,
  };
}

/**
 * Read-only status route for the Client settings page. It deliberately exposes
 * no control endpoint; microphone/TTS commands go through the Runtime protocol.
 */
export function registerStatusRoute(
  ctx: HostContext,
  manager: RuntimeManager,
  enabled: boolean,
): () => void {
  const webServer: WebServer | undefined = ctx.webServer ?? ctx.get<WebServer>('webServer', false);
  if (!enabled || !webServer) return () => {};

  return webServer.register({
    kind: 'prefix',
    path: ROUTE_PREFIX,
    handler: (req: IncomingMessage, res: ServerResponse) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1');
      if (req.method === 'GET' && url.pathname === `${ROUTE_PREFIX}/status`) {
        sendJson(res, 200, statusPayload(manager.status));
        return;
      }
      sendJson(res, 404, { error: 'not_found' });
    },
  });
}

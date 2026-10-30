import type { AddressInfo } from 'node:net';

import { afterEach, describe, expect, it } from 'vitest';
import { WebSocketServer } from 'ws';

import { RuntimeClient } from '../src/host/runtime-client.js';

const servers: WebSocketServer[] = [];

afterEach(() => {
  for (const server of servers.splice(0)) server.close();
});

async function startFakeRuntime(
  validToken: string,
): Promise<{ port: number; wss: WebSocketServer }> {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  servers.push(wss);
  await new Promise<void>((resolve) => wss.once('listening', resolve));
  wss.on('connection', (socket) => {
    socket.on('message', (raw) => {
      const message = JSON.parse(raw.toString()) as { type?: string; token?: string };
      if (message.type !== 'auth') return;
      if (message.token !== validToken) {
        socket.send(
          JSON.stringify({ type: 'auth.error', code: 'auth_failed', message: 'bad token' }),
        );
        return;
      }
      socket.send(JSON.stringify({ type: 'auth.ok', protocolVersion: 1, runtimeVersion: '0.1.0' }));
      socket.send(
        JSON.stringify({
          version: 1,
          id: 'ready',
          sessionId: 'runtime',
          sequence: 1,
          timestamp: 1,
          type: 'runtime.ready',
          payload: {
            runtimeVersion: '0.1.0',
            protocolVersion: 1,
            capabilities: [],
          },
        }),
      );
    });
  });
  const port = (wss.address() as AddressInfo).port;
  return { port, wss };
}

describe('RuntimeClient', () => {
  it('authenticates and becomes ready', async () => {
    const { port } = await startFakeRuntime('secret');
    const events: string[] = [];
    const client = new RuntimeClient({ onEvent: (event) => events.push(event.type) });
    await client.connect({
      pid: process.pid,
      host: '127.0.0.1',
      port,
      token: 'secret',
      runtimeVersion: '0.1.0',
      protocolVersion: 1,
      startedAt: '2026-10-30T00:00:00+00:00',
    });
    expect(client.state).toBe('ready');
    expect(events).toContain('runtime.ready');
    expect(client.send('ping', { pingId: 'p1' })).toBe(true);
    client.close();
    expect(client.state).toBe('closed');
  });

  it('rejects an invalid token', async () => {
    const { port } = await startFakeRuntime('secret');
    const client = new RuntimeClient({ connectTimeoutMs: 2_000 });
    await expect(
      client.connect({
        pid: process.pid,
        host: '127.0.0.1',
        port,
        token: 'wrong',
        runtimeVersion: '0.1.0',
        protocolVersion: 1,
        startedAt: '2026-10-30T00:00:00+00:00',
      }),
    ).rejects.toThrow(/bad token/);
    client.close();
  });

  it('closes when the heartbeat is not answered', async () => {
    const { port } = await startFakeRuntime('secret');
    const states: string[] = [];
    const client = new RuntimeClient({
      heartbeatIntervalMs: 30,
      heartbeatTimeoutMs: 60,
      onState: (state) => states.push(state),
    });
    await client.connect({
      pid: process.pid,
      host: '127.0.0.1',
      port,
      token: 'secret',
      runtimeVersion: '0.1.0',
      protocolVersion: 1,
      startedAt: '2026-10-30T00:00:00+00:00',
    });
    await new Promise((resolve) => setTimeout(resolve, 180));
    expect(states).toContain('closed');
    expect(client.state).toBe('closed');
    client.close();
  });
});

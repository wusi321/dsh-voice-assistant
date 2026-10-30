import { readFile } from 'node:fs/promises';
import { homedir, platform } from 'node:os';
import { join } from 'node:path';

/** Discovery file written by the Python Runtime. */
export interface DiscoveryInfo {
  readonly pid: number;
  readonly host: string;
  readonly port: number;
  readonly token: string;
  readonly runtimeVersion: string;
  readonly protocolVersion: number;
  readonly startedAt: string;
}

export interface DiscoveryPathInputs {
  readonly platform?: NodeJS.Platform;
  readonly env?: NodeJS.ProcessEnv;
  readonly home?: string;
}

/** Platform-specific default discovery path; keep in sync with the Python app dirs. */
export function discoveryPathFor(input: DiscoveryPathInputs = {}): string {
  const os = input.platform ?? platform();
  const env = input.env ?? process.env;
  const home = input.home ?? homedir();
  if (os === 'win32') {
    const base = env.LOCALAPPDATA ?? join(home, 'AppData', 'Local');
    return join(base, 'dsh-voice-assistant', 'runtime.json');
  }
  if (os === 'darwin') {
    return join(home, 'Library', 'Application Support', 'dsh-voice-assistant', 'runtime.json');
  }
  const base = env.XDG_DATA_HOME ?? join(home, '.local', 'share');
  return join(base, 'dsh-voice-assistant', 'runtime.json');
}

export function parseDiscovery(raw: string): DiscoveryInfo {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object') throw new Error('discovery file must be an object');
  const record = value as Record<string, unknown>;
  const pid = record.pid;
  const host = record.host;
  const port = record.port;
  const token = record.token;
  const runtimeVersion = record.runtimeVersion;
  const protocolVersion = record.protocolVersion;
  const startedAt = record.startedAt;
  if (typeof pid !== 'number' || !Number.isInteger(pid) || pid <= 0) {
    throw new Error('discovery.pid must be a positive integer');
  }
  if (host !== '127.0.0.1') throw new Error('discovery.host must be 127.0.0.1');
  if (typeof port !== 'number' || !Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error('discovery.port is invalid');
  }
  if (typeof token !== 'string' || token.length < 16) {
    throw new Error('discovery.token is missing or too short');
  }
  if (typeof runtimeVersion !== 'string' || runtimeVersion.length === 0) {
    throw new Error('discovery.runtimeVersion is missing');
  }
  if (typeof protocolVersion !== 'number' || !Number.isInteger(protocolVersion) || protocolVersion < 1) {
    throw new Error('discovery.protocolVersion is invalid');
  }
  if (typeof startedAt !== 'string' || startedAt.length === 0) {
    throw new Error('discovery.startedAt is missing');
  }
  return { pid, host, port, token, runtimeVersion, protocolVersion, startedAt };
}

export async function readDiscovery(path: string): Promise<DiscoveryInfo | null> {
  try {
    return parseDiscovery(await readFile(path, 'utf8'));
  } catch {
    return null;
  }
}

export function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Poll for a discovery file whose process is alive. */
export async function waitForDiscovery(
  path: string,
  timeoutMs: number,
  intervalMs = 100,
): Promise<DiscoveryInfo | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() <= deadline) {
    const info = await readDiscovery(path);
    if (info && isProcessAlive(info.pid)) return info;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return null;
}

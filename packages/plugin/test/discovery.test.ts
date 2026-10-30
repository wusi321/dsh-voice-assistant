import { describe, expect, it } from 'vitest';

import {
  discoveryPathFor,
  isProcessAlive,
  parseDiscovery,
} from '../src/host/discovery.js';

const valid = {
  pid: process.pid,
  host: '127.0.0.1',
  port: 4567,
  token: 'x'.repeat(32),
  runtimeVersion: '0.1.0',
  protocolVersion: 1,
  startedAt: '2026-10-30T00:00:00+00:00',
};

describe('discovery', () => {
  it('computes a Windows path', () => {
    const path = discoveryPathFor({
      platform: 'win32',
      env: { LOCALAPPDATA: 'C:\\Users\\me\\AppData\\Local' },
      home: 'C:\\Users\\me',
    });
    expect(path.toLowerCase()).toContain('dsh-voice-assistant');
    expect(path.endsWith('runtime.json')).toBe(true);
  });

  it('computes a Linux path', () => {
    const path = discoveryPathFor({
      platform: 'linux',
      env: { XDG_DATA_HOME: '/home/me/.local/share' },
      home: '/home/me',
    });
    expect(path.replaceAll('\\', '/')).toBe(
      '/home/me/.local/share/dsh-voice-assistant/runtime.json',
    );
  });

  it('parses a valid discovery record', () => {
    expect(parseDiscovery(JSON.stringify(valid))).toEqual(valid);
  });

  it('rejects a non-loopback host', () => {
    expect(() => parseDiscovery(JSON.stringify({ ...valid, host: '0.0.0.0' }))).toThrow(
      /127.0.0.1/,
    );
  });

  it('rejects a short token', () => {
    expect(() => parseDiscovery(JSON.stringify({ ...valid, token: 'short' }))).toThrow(/token/);
  });

  it('rejects an invalid port', () => {
    expect(() => parseDiscovery(JSON.stringify({ ...valid, port: 0 }))).toThrow(/port/);
  });

  it('checks process liveness for this process', () => {
    expect(isProcessAlive(process.pid)).toBe(true);
    expect(isProcessAlive(999_999)).toBe(false);
  });
});

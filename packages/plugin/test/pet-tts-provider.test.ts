import { describe, expect, it, vi } from 'vitest';

import type { Config } from '../src/host/config.js';
import { PetTtsProvider, type PetVoiceProvider } from '../src/host/pet-tts-provider.js';

const base: Config = {
  autoStart: false,
  runtimeCommand: 'voice-runtime',
  discoveryPath: '/tmp/runtime.json',
  startupTimeoutMs: 1_000,
  reconnectMinMs: 100,
  reconnectMaxMs: 1_000,
  fakeAudio: true,
  statusRoute: true,
  sessionStrategy: 'active',
  fixedSessionId: '',
  cancelTimeoutMs: 1_000,
  speakAssistant: true,
  petEnabled: true,
  petBaseUrl: 'http://127.0.0.1:3080',
  petId: 'main',
  petLockTtlMs: 60_000,
  petBridgeTimeoutMs: 1_000,
  petBubbleEnabled: true,
  petAnimationEnabled: true,
  petUseWorkStatus: true,
  petTtsProvider: true,
  petTtsProviderCommand: '',
};

function api() {
  let registered: PetVoiceProvider | undefined;
  const dispose = vi.fn();
  const register = vi.fn((provider: PetVoiceProvider) => {
    registered = provider;
    return dispose;
  });
  return {
    api: { voice: { register, list: () => ({ builtin: ['edge'], external: [] }) } },
    register,
    dispose,
    provider: () => registered,
  };
}

function context(value: unknown): any {
  return { get: vi.fn((name: string) => (name === 'petApi7340' ? value : undefined)) };
}

describe('PetTtsProvider', () => {
  it('stays disabled by default', () => {
    const { api: voice } = api();
    const provider = new PetTtsProvider(context(voice), { ...base, petTtsProvider: false });
    provider.start();
    expect(provider.status.state).toBe('disabled');
  });

  it('registers only with a real synthesizer and enforces the contract', async () => {
    const { api: voice, register, dispose, provider: registered } = api();
    const provider = new PetTtsProvider(
      context(voice),
      base,
      async ({ text }) => new Uint8Array([0xff, 0xfb, 0x90, 0x64, text.length]),
    );
    provider.start();
    expect(provider.status.state).toBe('registered');
    expect(register).toHaveBeenCalledOnce();
    const def = registered();
    expect(def?.id).toBe('dsh-voice-runtime');
    await expect(def!.synthesize({ text: '你好', rate: '+0%' })).resolves.toBeInstanceOf(
      Uint8Array,
    );
    await expect(def!.synthesize({ text: 'x'.repeat(501), rate: '+0%' })).rejects.toThrow(
      /too long/,
    );
    provider.stop();
    expect(dispose).toHaveBeenCalledOnce();
  });

  it('is unsupported without petApi7340 or synthesizer', () => {
    const noApi = new PetTtsProvider(context(undefined), base);
    noApi.start();
    expect(noApi.status.state).toBe('unsupported');

    const withApi = api();
    const noSynth = new PetTtsProvider(context(withApi.api), base);
    noSynth.start();
    expect(noSynth.status.state).toBe('unsupported');
    expect(withApi.register).not.toHaveBeenCalled();
  });

  it('rejects empty synthesizer output', async () => {
    const { api: voice, provider: registered } = api();
    const provider = new PetTtsProvider(context(voice), base, async () => new Uint8Array());
    provider.start();
    await expect(registered()!.synthesize({ text: '你好', rate: '+0%' })).rejects.toThrow(
      /no bytes/,
    );
  });

  it('rejects a non-MP3 payload instead of relabeling it', async () => {
    const { api: voice, provider: registered } = api();
    const provider = new PetTtsProvider(
      context(voice),
      base,
      async () => new Uint8Array([0x52, 0x49, 0x46, 0x46]),
    );
    provider.start();
    await expect(registered()!.synthesize({ text: '你好', rate: '+0%' })).rejects.toThrow(
      /non-MP3/,
    );
  });
});

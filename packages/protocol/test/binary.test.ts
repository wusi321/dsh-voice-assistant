import { describe, expect, it } from 'vitest';
import {
  PCM_FRAME_HEADER_BYTES,
  decodePcmFrame,
  encodePcmFrame,
  pcmFrameCount,
  type PcmFrame,
} from '../src/index.js';

function frame(overrides: Partial<PcmFrame> = {}): PcmFrame {
  return {
    sequence: 7,
    timestampMs: 1234,
    sampleRate: 16_000,
    channels: 1,
    format: 1,
    flags: { discontinuity: false, final: false },
    frameCount: 4,
    data: new Uint8Array([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]),
    ...overrides,
  };
}

describe('binary PCM frame', () => {
  it('round-trips one mono frame', () => {
    const original = frame();
    const encoded = encodePcmFrame(original);
    expect(encoded.byteLength).toBe(PCM_FRAME_HEADER_BYTES + 8);
    const decoded = decodePcmFrame(encoded);
    expect(decoded).toMatchObject({
      sequence: 7,
      timestampMs: 1234,
      sampleRate: 16_000,
      channels: 1,
      format: 1,
      frameCount: 4,
      flags: { discontinuity: false, final: false },
    });
    expect([...decoded.data]).toEqual([...original.data]);
  });

  it('round-trips stereo with flags', () => {
    const original = frame({
      channels: 2,
      frameCount: 2,
      flags: { discontinuity: true, final: true },
      data: new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]),
    });
    const decoded = decodePcmFrame(encodePcmFrame(original));
    expect(decoded.channels).toBe(2);
    expect(decoded.flags.discontinuity).toBe(true);
    expect(decoded.flags.final).toBe(true);
  });

  it('rejects bad magic', () => {
    const encoded = encodePcmFrame(frame());
    encoded[0] = 0;
    expect(() => decodePcmFrame(encoded)).toThrow(/bad magic/);
  });

  it('rejects an unsupported frame version', () => {
    const encoded = encodePcmFrame(frame());
    encoded[4] = 2;
    expect(() => decodePcmFrame(encoded)).toThrow(/unsupported frame version/);
  });

  it('rejects a truncated payload', () => {
    const encoded = encodePcmFrame(frame());
    expect(() => decodePcmFrame(encoded.subarray(0, encoded.byteLength - 1))).toThrow(
      /expected/,
    );
  });

  it('rejects an invalid sample rate', () => {
    expect(() => encodePcmFrame(frame({ sampleRate: 4_000 }))).toThrow(/sampleRate/);
  });

  it('rejects a misaligned payload', () => {
    expect(() => encodePcmFrame(frame({ frameCount: 2 }))).toThrow(/payload/);
  });

  it('counts PCM frames for mono and stereo', () => {
    expect(pcmFrameCount(320, 1)).toBe(160);
    expect(pcmFrameCount(640, 2)).toBe(160);
    expect(() => pcmFrameCount(321, 1)).toThrow(/aligned/);
  });
});

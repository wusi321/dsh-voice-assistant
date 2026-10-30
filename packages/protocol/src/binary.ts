import {
  PCM_FORMAT,
  PCM_FRAME_HEADER_BYTES,
  PCM_FRAME_MAGIC,
  type PcmFormat,
} from './version.js';

/** Optional flags carried by a PCM frame. */
export interface PcmFrameFlags {
  /** The sender dropped audio before this frame; the receiver must reset timing. */
  readonly discontinuity: boolean;
  /** The final frame of one utterance. */
  readonly final: boolean;
}

/** One binary PCM frame: a fixed header followed by little-endian PCM samples. */
export interface PcmFrame {
  readonly sequence: number;
  /** Milliseconds since the sender's session start. Wraps after ~49 days. */
  readonly timestampMs: number;
  readonly sampleRate: number;
  readonly channels: number;
  readonly format: PcmFormat;
  readonly flags: PcmFrameFlags;
  /** Number of sample frames (per channel) in `data`. */
  readonly frameCount: number;
  /** Raw PCM payload, interleaved by channel. */
  readonly data: Uint8Array;
}

const MAGIC_BYTES = [0x56, 0x41, 0x50, 0x31] as const; // "VAP1"
const HEADER_LENGTH = PCM_FRAME_HEADER_BYTES;
const FLAG_DISCONTINUITY = 1 << 0;
const FLAG_FINAL = 1 << 1;
const MAX_FRAME_COUNT = 48_000;

function fail(message: string): never {
  throw new RangeError(`invalid PCM frame: ${message}`);
}

function byteView(input: ArrayBuffer | Uint8Array): Uint8Array {
  return input instanceof Uint8Array ? input : new Uint8Array(input);
}

function assertHeaderFields(frame: Omit<PcmFrame, 'data'>): void {
  if (!Number.isInteger(frame.sequence) || frame.sequence < 0 || frame.sequence > 0xffffffff) {
    fail('sequence must be a uint32');
  }
  if (
    !Number.isInteger(frame.timestampMs) ||
    frame.timestampMs < 0 ||
    frame.timestampMs > 0xffffffff
  ) {
    fail('timestampMs must be a uint32');
  }
  if (!Number.isInteger(frame.sampleRate) || frame.sampleRate < 8_000 || frame.sampleRate > 192_000) {
    fail('sampleRate must be 8000..192000');
  }
  if (!Number.isInteger(frame.channels) || frame.channels < 1 || frame.channels > 2) {
    fail('channels must be 1 or 2');
  }
  if (frame.format !== PCM_FORMAT.PCM16_LE) {
    fail('unsupported sample format');
  }
  if (
    !Number.isInteger(frame.frameCount) ||
    frame.frameCount <= 0 ||
    frame.frameCount > MAX_FRAME_COUNT
  ) {
    fail(`frameCount must be 1..${MAX_FRAME_COUNT}`);
  }
}

/** Encode one frame into a single binary message. */
export function encodePcmFrame(frame: PcmFrame): Uint8Array {
  assertHeaderFields(frame);
  const expectedBytes = frame.frameCount * frame.channels * 2;
  if (frame.data.byteLength !== expectedBytes) {
    fail(`payload is ${frame.data.byteLength} bytes, expected ${expectedBytes}`);
  }

  const out = new Uint8Array(HEADER_LENGTH + frame.data.byteLength);
  const view = new DataView(out.buffer);
  out.set(MAGIC_BYTES, 0);
  view.setUint8(4, 1); // frame version
  view.setUint8(5, (frame.flags.discontinuity ? FLAG_DISCONTINUITY : 0) | (frame.flags.final ? FLAG_FINAL : 0));
  view.setUint16(6, HEADER_LENGTH, true);
  view.setUint32(8, frame.sequence, true);
  view.setUint32(12, frame.timestampMs, true);
  view.setUint32(16, frame.sampleRate, true);
  view.setUint16(20, frame.channels, true);
  view.setUint8(22, frame.format);
  view.setUint8(23, 0); // reserved
  view.setUint32(24, frame.frameCount, true);
  out.set(frame.data, HEADER_LENGTH);
  return out;
}

/** Decode and validate one binary message. Throws `RangeError` on malformed input. */
export function decodePcmFrame(input: ArrayBuffer | Uint8Array): PcmFrame {
  const bytes = byteView(input);
  if (bytes.byteLength < HEADER_LENGTH) fail(`need at least ${HEADER_LENGTH} header bytes`);
  if (
    bytes[0] !== MAGIC_BYTES[0] ||
    bytes[1] !== MAGIC_BYTES[1] ||
    bytes[2] !== MAGIC_BYTES[2] ||
    bytes[3] !== MAGIC_BYTES[3]
  ) {
    fail(`bad magic (expected ${PCM_FRAME_MAGIC})`);
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const version = view.getUint8(4);
  if (version !== 1) fail(`unsupported frame version ${version}`);
  const headerLength = view.getUint16(6, true);
  if (headerLength !== HEADER_LENGTH) fail(`header length ${headerLength}, expected ${HEADER_LENGTH}`);
  const flagsByte = view.getUint8(5);
  const format = view.getUint8(22);
  if (format !== PCM_FORMAT.PCM16_LE) fail(`unsupported format ${format}`);
  const frameCount = view.getUint32(24, true);
  const frame: Omit<PcmFrame, 'data'> = {
    sequence: view.getUint32(8, true),
    timestampMs: view.getUint32(12, true),
    sampleRate: view.getUint32(16, true),
    channels: view.getUint16(20, true),
    format: format as PcmFormat,
    flags: {
      discontinuity: (flagsByte & FLAG_DISCONTINUITY) !== 0,
      final: (flagsByte & FLAG_FINAL) !== 0,
    },
    frameCount,
  };
  assertHeaderFields(frame);

  const expectedBytes = HEADER_LENGTH + frameCount * frame.channels * 2;
  if (bytes.byteLength !== expectedBytes) {
    fail(`message is ${bytes.byteLength} bytes, expected ${expectedBytes}`);
  }
  return {
    ...frame,
    data: bytes.subarray(HEADER_LENGTH, expectedBytes),
  };
}

/** Number of PCM frames in a byte length for a given channel count. */
export function pcmFrameCount(byteLength: number, channels: number): number {
  if (channels < 1 || channels > 2) fail('channels must be 1 or 2');
  if (byteLength < 0 || byteLength % (channels * 2) !== 0) {
    fail('payload length is not aligned to PCM16 frames');
  }
  return byteLength / (channels * 2);
}

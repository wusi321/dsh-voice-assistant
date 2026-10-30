/** Sentence segmentation and sanitization for speech output. */

export function sanitizeForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function firstBoundary(text: string): number {
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index] ?? '';
    if ('。！？!?；;\n'.includes(char)) return index;
    if (char === '.' && (index === text.length - 1 || /\s/.test(text[index + 1] ?? ''))) {
      return index;
    }
  }
  return -1;
}

/**
 * Accumulates streamed assistant text and returns speakable sentences.
 * Markdown/code/URLs are removed before any text reaches TTS.
 */
export class SentenceSegmenter {
  private buffer = '';
  private readonly maxChars: number;

  constructor(maxChars = 180) {
    this.maxChars = maxChars;
  }

  reset(): void {
    this.buffer = '';
  }

  push(delta: string): string[] {
    if (!delta) return [];
    this.buffer += delta;
    const out: string[] = [];
    for (;;) {
      const boundary = firstBoundary(this.buffer);
      if (boundary < 0) break;
      const sentence = this.buffer.slice(0, boundary + 1);
      this.buffer = this.buffer.slice(boundary + 1);
      const clean = sanitizeForSpeech(sentence);
      if (clean) out.push(clean);
    }
    while (this.buffer.length > this.maxChars) {
      const window = this.buffer.slice(0, this.maxChars);
      const split = Math.max(
        window.lastIndexOf(' '),
        window.lastIndexOf('，'),
        window.lastIndexOf(','),
      );
      const cut = split > 20 ? split + 1 : this.maxChars;
      const sentence = sanitizeForSpeech(this.buffer.slice(0, cut));
      this.buffer = this.buffer.slice(cut);
      if (sentence) out.push(sentence);
    }
    return out;
  }

  flush(): string[] {
    const sentence = sanitizeForSpeech(this.buffer);
    this.buffer = '';
    return sentence ? [sentence] : [];
  }
}

/** Split complete text into sentences (used by tests and non-stream callers). */
export function splitSentences(text: string, maxChars = 180): string[] {
  const segmenter = new SentenceSegmenter(maxChars);
  return [...segmenter.push(text), ...segmenter.flush()];
}

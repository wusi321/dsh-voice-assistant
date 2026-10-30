import { describe, expect, it } from 'vitest';

import { SentenceSegmenter, sanitizeForSpeech, splitSentences } from '../src/host/sentence.js';

describe('sentence segmentation', () => {
  it('splits Chinese sentences', () => {
    const segmenter = new SentenceSegmenter();
    expect(segmenter.push('你好。请打开台灯！')).toEqual(['你好。', '请打开台灯！']);
    expect(segmenter.flush()).toEqual([]);
  });

  it('splits English sentences at whitespace boundaries', () => {
    expect(splitSentences('Hello there. How are you? Fine.')).toEqual([
      'Hello there.',
      'How are you?',
      'Fine.',
    ]);
  });

  it('flushes an unterminated final sentence', () => {
    const segmenter = new SentenceSegmenter();
    expect(segmenter.push('没有句号的内容')).toEqual([]);
    expect(segmenter.flush()).toEqual(['没有句号的内容']);
  });

  it('strips code, markdown and URLs before speaking', () => {
    expect(sanitizeForSpeech('看这里 https://example.com ```py\nprint(1)\n``` **重要**')).toBe(
      '看这里 重要',
    );
    expect(sanitizeForSpeech('[文档](https://example.com) 内容')).toBe('文档 内容');
  });

  it('caps long unpunctuated text', () => {
    const segmenter = new SentenceSegmenter(20);
    const out = segmenter.push('一二三四五六七八九十一二三四五六七八九十一二三四五');
    expect(out.length).toBeGreaterThan(0);
    expect(out[0]?.length).toBeLessThanOrEqual(120);
  });
});

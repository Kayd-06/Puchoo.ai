import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import {
  ResultSpeechControls,
  buildResultSpeechPayload,
  splitResultSpeech,
  isActiveResultSpeech,
  resolveResultSpeechLanguage,
  stopResultSpeech,
} from '../pages/AskData';

afterEach(() => {
  vi.restoreAllMocks();
});

it('builds speech from the visible answer without speaking hidden SQL or question', () => {
  const result = {
    presentation: {
      headline: 'आपका कुल खर्च 2,000 है।',
      detail: 'यह पिछले महीने का सत्यापित योग है।',
    },
    record: {
      question: 'मेरे खर्चे बताओ',
      sql: 'SELECT secret_column FROM expenses',
      rows: [{ secret_column: 'should never be spoken' }],
    },
  };

  const payload = buildResultSpeechPayload(result.presentation);

  expect(payload).toBe('आपका कुल खर्च 2,000 है।\n\nयह पिछले महीने का सत्यापित योग है।');
  expect(payload).not.toContain(result.record.question);
  expect(payload).not.toContain(result.record.sql);
  expect(payload).not.toContain(result.record.rows[0].secret_column);
  expect(buildResultSpeechPayload({ headline: 'x'.repeat(2001) })).toHaveLength(2001);
});

it('prefers the result language before the current composer language', () => {
  expect(resolveResultSpeechLanguage({ record: { language_code: 'hi-IN' } }, 'en-IN')).toBe(
    'hi-IN',
  );
  expect(resolveResultSpeechLanguage({ record: {} }, 'ta-IN')).toBe('ta-IN');
  expect(resolveResultSpeechLanguage({ record: {} }, null)).toBe('en-IN');
});

it('stops audio and releases its object URL when a report is replaced or unmounted', () => {
  const audio = { pause: vi.fn(), removeAttribute: vi.fn(), load: vi.fn() };
  const audioRef = { current: audio };
  const urlRef = { current: 'blob:result-audio' };
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

  stopResultSpeech(audioRef, urlRef);

  expect(audio.pause).toHaveBeenCalledOnce();
  expect(audio.removeAttribute).toHaveBeenCalledWith('src');
  expect(audio.load).toHaveBeenCalledOnce();
  expect(revoke).toHaveBeenCalledWith('blob:result-audio');
  expect(audioRef.current).toBeNull();
  expect(urlRef.current).toBeNull();
});

it('ignores a resume completion once the audio or playback request is no longer current', () => {
  const audio = {};
  const audioRef = { current: audio };
  const requestRef = { current: 4 };

  expect(isActiveResultSpeech(audioRef, audio, requestRef, 4)).toBe(true);
  audioRef.current = null;
  expect(isActiveResultSpeech(audioRef, audio, requestRef, 4)).toBe(false);
  audioRef.current = audio;
  requestRef.current = 5;
  expect(isActiveResultSpeech(audioRef, audio, requestRef, 4)).toBe(false);
});

it('exposes user-controlled listen, pause or resume, and stop actions with a polite status', () => {
  const onPlay = vi.fn();
  const onPauseResume = vi.fn();
  const onStop = vi.fn();
  const { rerender } = render(
    <ResultSpeechControls
      speechState="idle"
      speechError=""
      onPlay={onPlay}
      onPauseResume={onPauseResume}
      onStop={onStop}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Listen to answer' }));
  expect(onPlay).toHaveBeenCalledOnce();
  expect(screen.getByRole('status')).toHaveTextContent('Ready to play the answer');

  rerender(
    <ResultSpeechControls
      speechState="playing"
      speechError=""
      onPlay={onPlay}
      onPauseResume={onPauseResume}
      onStop={onStop}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Pause answer' }));
  fireEvent.click(screen.getByRole('button', { name: 'Stop reading answer' }));
  expect(onPauseResume).toHaveBeenCalledOnce();
  expect(onStop).toHaveBeenCalledOnce();
  expect(screen.getByRole('status')).toHaveTextContent('Playing full report');

  rerender(
    <ResultSpeechControls
      speechState="paused"
      speechError=""
      onPlay={onPlay}
      onPauseResume={onPauseResume}
      onStop={onStop}
    />,
  );
  expect(screen.getByRole('button', { name: 'Resume answer' })).toBeInTheDocument();
});

it('reads every localized row including zero and false without hidden raw text', () => {
  const result = {
    presentation: {
      headline: 'दो परिणाम',
      detail: 'विवरण',
      language_code: 'hi-IN',
      column_labels: { status: 'स्थिति', amount: 'राशि', active: 'सक्रिय' },
      display_rows: [
        { status: 'भुगतान हुआ', amount: 0, active: false },
        { status: 'बाकी', amount: 200, active: true },
      ],
    },
    record: {
      columns: ['status', 'amount', 'active'],
      rows: [
        { status: 'Paid', amount: 0, active: false },
        { status: 'Pending', amount: 200, active: true },
      ],
      sql: 'hidden SQL',
    },
  };
  const text = buildResultSpeechPayload(result.presentation, result.record);
  expect(text).toContain('स्थिति: भुगतान हुआ');
  expect(text).toContain('राशि: 0');
  expect(text).toContain('सक्रिय: false');
  expect(text).toContain('स्थिति: बाकी');
  expect(text).toContain('राशि: 200');
  expect(text).not.toContain('Paid');
  expect(text).not.toContain('hidden SQL');
  expect(resolveResultSpeechLanguage(result, 'en-IN')).toBe('hi-IN');
});

it('splits long reports without dropping any cells or breaking Unicode characters', () => {
  const text = 'राशि: 200। '.repeat(500) + '😀'.repeat(1500);
  const clips = splitResultSpeech(text);
  expect(clips.length).toBeGreaterThan(1);
  expect(clips.every((clip) => clip.length <= 2000 && clip.length > 0)).toBe(true);
  expect(clips.join('')).toBe(text);
  expect(clips.every((clip) => !/[\uD800-\uDBFF]$/.test(clip))).toBe(true);
});

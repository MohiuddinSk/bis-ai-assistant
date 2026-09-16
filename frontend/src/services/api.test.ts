import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  ApiError,
  askQuestion,
  CHAT_DEFAULT_TIMEOUT_MS,
  chatTimeoutMs,
  getHealth,
  HEALTH_TIMEOUT_MS,
  isFreeNgrokApiBase,
  ngrokBypassHeadersForBase,
  parseChatTimeoutMs,
} from './api';

it('adds the ngrok bypass header only for exact approved free development origins', () => {
  for (const base of ['https://demo-account.ngrok-free.app', 'https://demo-account.ngrok-free.dev']) {
    expect(isFreeNgrokApiBase(base)).toBe(true);
    expect(ngrokBypassHeadersForBase(base)).toEqual({ 'ngrok-skip-browser-warning': '1' });
  }
  for (const base of [
    '', 'http://demo-account.ngrok-free.dev', 'https://localhost:8000', 'https://example.com',
    'https://demo-account.ngrok-free.dev/path', 'https://demo-account.ngrok-free.dev?x=1',
    'https://demo-account.ngrok-free.dev#fragment', 'https://demo-account.ngrok-free.dev:443',
    'https://demo-account.ngrok-free.dev.evil.example', 'https://notngrok-free.dev',
    'https://demo-account.ngrok-free.dev@evil.example', 'https://ngrok-free.dev',
  ]) {
    expect(isFreeNgrokApiBase(base)).toBe(false);
    expect(ngrokBypassHeadersForBase(base)).toEqual({});
  }
});

const chatPayload = {
  answer: 'IS 15644 is the primary standard.',
  grounded: true,
  insufficient_evidence: false,
  citations: [],
};

const response = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body });

function abortablePendingRequest(signals: AbortSignal[]) {
  return vi.fn((_url: string, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      const signal = init?.signal as AbortSignal;
      signals.push(signal);
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('keeps a chat request active beyond the former 30-second deadline', async () => {
  let resolveRequest!: (value: unknown) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveRequest = resolve; })));
  const pending = askQuestion('Which standard applies to a battery-operated toy?');

  await vi.advanceTimersByTimeAsync(30_001);
  expect(fetch).toHaveBeenCalledOnce();
  resolveRequest(response(chatPayload));
  await expect(pending).resolves.toEqual(chatPayload);
});

it('times out a chat request at the configured default deadline', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', abortablePendingRequest(signals));
  const pending = askQuestion('question');
  const rejected = expect(pending).rejects.toMatchObject({ friendly: 'The request timed out. Please try again.' });

  await vi.advanceTimersByTimeAsync(chatTimeoutMs - 1);
  expect(signals[0].aborted).toBe(false);
  await vi.advanceTimersByTimeAsync(1);
  await rejected;
});

it('keeps health checks on their shorter deadline', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', abortablePendingRequest(signals));
  const pending = getHealth();
  const rejected = expect(pending).rejects.toMatchObject({ friendly: 'The request timed out. Please try again.' });

  await vi.advanceTimersByTimeAsync(HEALTH_TIMEOUT_MS);
  await rejected;
  expect(HEALTH_TIMEOUT_MS).toBeLessThan(chatTimeoutMs);
});

it('uses a fresh AbortController for retry requests', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', abortablePendingRequest(signals));
  const first = askQuestion('question');
  const firstRejected = expect(first).rejects.toBeInstanceOf(ApiError);
  await vi.advanceTimersByTimeAsync(chatTimeoutMs);
  await firstRejected;

  const second = askQuestion('question');
  expect(signals).toHaveLength(2);
  expect(signals[0]).not.toBe(signals[1]);
  expect(signals[1].aborted).toBe(false);
  const secondRejected = expect(second).rejects.toBeInstanceOf(ApiError);
  await vi.advanceTimersByTimeAsync(chatTimeoutMs);
  await secondRejected;
});

it('renders a successful service response before its deadline', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(chatPayload)));
  await expect(askQuestion('question')).resolves.toEqual(chatPayload);
  expect(vi.getTimerCount()).toBe(0);
});

it('does not mislabel an HTTP provider error as a frontend timeout', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'provider error' }, false, 503)));
  await expect(askQuestion('question')).rejects.toMatchObject({
    friendly: 'The guidance service is temporarily unavailable. Please try again.',
  });
});

it('falls back safely for invalid public chat timeout values', () => {
  expect(chatTimeoutMs).toBe(CHAT_DEFAULT_TIMEOUT_MS);
  expect(parseChatTimeoutMs('not-a-number')).toBe(CHAT_DEFAULT_TIMEOUT_MS);
  expect(parseChatTimeoutMs(999)).toBe(CHAT_DEFAULT_TIMEOUT_MS);
  expect(parseChatTimeoutMs(300_001)).toBe(CHAT_DEFAULT_TIMEOUT_MS);
  expect(parseChatTimeoutMs('90000')).toBe(CHAT_DEFAULT_TIMEOUT_MS);
});

it('cleans up the request timer after an externally aborted health check', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', abortablePendingRequest(signals));
  const controller = new AbortController();
  const pending = getHealth(controller.signal);
  const rejected = expect(pending).rejects.toMatchObject({ friendly: 'The request was cancelled. Please try again.' });
  controller.abort();
  await rejected;
  expect(vi.getTimerCount()).toBe(0);
});

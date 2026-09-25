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
  openSourcePdf,
  parseChatTimeoutMs,
  sourceDocumentPageFragment,
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

function pdfResponse() {
  return {
    ok: true,
    headers: new Headers({ 'content-type': 'application/pdf' }),
    blob: vi.fn().mockResolvedValue(new Blob(['%PDF-1.7'], { type: 'application/pdf' })),
  };
}

function temporaryTab() {
  return {
    opener: window,
    close: vi.fn(),
    location: { replace: vi.fn() },
  } as unknown as Window;
}

it('fetches exact approved ngrok origins with the bypass header before navigating a synchronous blank tab to a Blob URL', async () => {
  for (const apiBase of ['https://demo-account.ngrok-free.app', 'https://demo-account.ngrok-free.dev']) {
    const tab = temporaryTab();
    const openTab = vi.fn(() => tab);
    const fetchFn = vi.fn().mockResolvedValue(pdfResponse());
    const createObjectURL = vi.fn(() => 'blob:source-pdf');

    const pending = openSourcePdf('product manual.pdf', 4, { apiBase, openTab, fetchFn, createObjectURL });
    expect(openTab).toHaveBeenCalledOnce();
    expect(fetchFn).toHaveBeenCalledWith(`${apiBase}/api/documents/product%20manual.pdf`, {
      headers: { 'ngrok-skip-browser-warning': '1' },
    });
    await pending;
    expect(tab.opener).toBeNull();
    expect(tab.location.replace).toHaveBeenCalledWith('blob:source-pdf#page=4');
    expect(tab.location.replace).not.toHaveBeenCalledWith(expect.stringContaining('ngrok-free'));
  }
});

it('does not attach a bypass header for hostile or lookalike document origins', async () => {
  for (const apiBase of [
    'https://demo-account.ngrok-free.dev.evil.example', 'https://user:pass@demo-account.ngrok-free.dev',
    'https://demo-account.ngrok-free.dev/path', 'https://demo-account.ngrok-free.dev:8443',
  ]) {
    const fetchFn = vi.fn().mockResolvedValue(pdfResponse());
    await openSourcePdf('source.pdf', 1, {
      apiBase, openTab: () => temporaryTab(), fetchFn, createObjectURL: () => 'blob:source-pdf',
    });
    expect(fetchFn.mock.calls[0][1]).toEqual({ headers: {} });
  }
});

it('omits unsafe document page fragments', () => {
  expect(sourceDocumentPageFragment(4)).toBe('#page=4');
  for (const page of [undefined, null, 0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
    expect(sourceDocumentPageFragment(page)).toBe('');
  }
});

it('closes the temporary tab and exposes only a safe error for HTTP or network failures', async () => {
  for (const fetchFn of [
    vi.fn().mockResolvedValue({ ok: false, headers: new Headers({ 'content-type': 'text/html' }), blob: vi.fn() }),
    vi.fn().mockRejectedValue(new Error('<html>backend failure</html>')),
  ]) {
    const tab = temporaryTab();
    await expect(openSourcePdf('source.pdf', 4, {
      apiBase: 'https://demo-account.ngrok-free.dev', openTab: () => tab, fetchFn,
    })).rejects.toMatchObject({ friendly: 'Unable to open the source PDF. Please try again.' });
    expect(tab.close).toHaveBeenCalledOnce();
    expect(tab.location.replace).not.toHaveBeenCalled();
  }
});

it('rejects non-PDF response types without opening their body in the tab', async () => {
  const tab = temporaryTab();
  const response = { ok: true, headers: new Headers({ 'content-type': 'text/html' }), blob: vi.fn() };
  await expect(openSourcePdf('source.pdf', 4, {
    openTab: () => tab, fetchFn: vi.fn().mockResolvedValue(response),
  })).rejects.toMatchObject({ friendly: 'Unable to open the source PDF. Please try again.' });
  expect(response.blob).not.toHaveBeenCalled();
  expect(tab.location.replace).not.toHaveBeenCalled();
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
    friendly: 'This request needs a service that is currently unavailable. Try another question or use the Compliance Wizard.',
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

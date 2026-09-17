import type { AssistantContext, Audience, ChatResponse, HealthResponse } from '../types/chat';
import type { ComplianceGuideResponse, ComplianceProfile } from '../types/compliance';

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const NGROK_SKIP_BROWSER_WARNING = 'ngrok-skip-browser-warning';

export function isFreeNgrokApiBase(value: string): boolean {
  try {
    if (!/^https:\/\/[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.ngrok-free\.(?:app|dev)$/i.test(value)) return false;
    const url = new URL(value);
    return url.protocol === 'https:'
      && !url.username && !url.password && !url.port
      && url.pathname === '/' && !url.search && !url.hash
      && /.+\.ngrok-free\.(?:app|dev)$/i.test(url.hostname);
  } catch {
    return false;
  }
}

export function ngrokBypassHeadersForBase(value: string): Record<string, string> {
  return isFreeNgrokApiBase(value) ? { [NGROK_SKIP_BROWSER_WARNING]: '1' } : {};
}

const ngrokBypassHeaders = ngrokBypassHeadersForBase(base);
export const HEALTH_TIMEOUT_MS = 8_000;
export const CHAT_DEFAULT_TIMEOUT_MS = 90_000;

export function parseChatTimeoutMs(value: unknown): number {
  const timeout = Number(value);
  return Number.isFinite(timeout) && timeout >= 1_000 && timeout <= 300_000
    ? timeout
    : CHAT_DEFAULT_TIMEOUT_MS;
}

export const chatTimeoutMs = parseChatTimeoutMs(import.meta.env.VITE_CHAT_TIMEOUT_MS);

export class ApiError extends Error {
  constructor(public readonly friendly: string) {
    super(friendly);
  }
}

async function request<T>(path: string, timeout: number, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  init.signal?.addEventListener('abort', () => controller.abort(), { once: true });
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout);

  try {
    const response = await fetch(`${base}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...ngrokBypassHeaders, ...init.headers },
    });
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError('The service returned an unreadable response. Please try again.');
    }
    if (!response.ok) {
      throw new ApiError(
        response.status === 422
          ? 'Please enter a valid question.'
          : response.status === 503
            ? 'This request needs a service that is currently unavailable. Try another question or use the Compliance Wizard.'
          : response.status >= 500
            ? 'The guidance service is temporarily unavailable. Please try again.'
            : 'Unable to complete that request.',
      );
    }
    if (path === '/api/chat' && (!body || typeof body !== 'object' || typeof (body as { answer?: unknown }).answer !== 'string')) {
      throw new ApiError('The service returned an unreadable response. Please try again.');
    }
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(timedOut ? 'The request timed out. Please try again.' : 'The request was cancelled. Please try again.');
    }
    throw new ApiError('Unable to reach the guidance service. Check your connection and try again.');
  } finally {
    window.clearTimeout(timer);
  }
}

export const getHealth = (signal?: AbortSignal) => request<HealthResponse>('/health', HEALTH_TIMEOUT_MS, { signal });
export const askQuestion = (
  question: string,
  audience: Audience = 'general',
  assistantContext?: AssistantContext,
  signal?: AbortSignal,
) =>
  request<ChatResponse>('/api/chat', chatTimeoutMs, {
    method: 'POST',
    body: JSON.stringify({
      question,
      top_k: 8,
      include_guidance: false,
      audience,
      ...(assistantContext ? { assistant_context: assistantContext } : {}),
    }),
    signal,
  });
export const getComplianceGuide = (profile: ComplianceProfile, signal?: AbortSignal) =>
  request<ComplianceGuideResponse>('/api/compliance/guide', chatTimeoutMs, {
    method: 'POST', body: JSON.stringify(profile), signal,
  });

import type { Audience, ChatResponse, HealthResponse } from '../types/chat';
import type { ComplianceGuideResponse, ComplianceProfile } from '../types/compliance';

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
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
      headers: { 'Content-Type': 'application/json', ...init.headers },
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
export const askQuestion = (question: string, audience: Audience = 'general') =>
  request<ChatResponse>('/api/chat', chatTimeoutMs, {
    method: 'POST',
    body: JSON.stringify({ question, top_k: 8, include_guidance: false, audience }),
  });
export const getComplianceGuide = (profile: ComplianceProfile, signal?: AbortSignal) =>
  request<ComplianceGuideResponse>('/api/compliance/guide', chatTimeoutMs, {
    method: 'POST', body: JSON.stringify(profile), signal,
  });

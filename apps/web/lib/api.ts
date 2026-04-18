// Typed fetch wrapper.
// - Authorization: Bearer <access> из in-memory store.
// - credentials: 'include' для refresh cookie.
// - При 401 один раз пытается POST /auth/refresh и ретраит запрос.
// - При NEXT_PUBLIC_USE_MOCK_API=true возвращает фикстуры без сетевых вызовов.

import { API_BASE_URL, API_PREFIX, USE_MOCK_API } from './env';
import { adminTokenStore, userTokenStore } from './auth';
import { ApiError, type RequestOptions } from './apiError';
import { mockApi } from './mockApi';
import type { ApiErrorShape } from './types';

export { ApiError };
export type { RequestOptions };

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE_URL}${API_PREFIX}${path}`);
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  return url.toString();
}

async function refreshAccessToken(scope: 'user' | 'admin'): Promise<string | null> {
  try {
    const path = scope === 'admin' ? '/admin/auth/refresh' : '/auth/refresh';
    const res = await fetch(buildUrl(path), {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { access_token?: string };
    if (data.access_token) {
      const store = scope === 'admin' ? adminTokenStore : userTokenStore;
      store.set(data.access_token);
      return data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

async function rawRequest<T>(path: string, opts: RequestOptions): Promise<T> {
  const scope = opts.scope ?? 'user';
  const store = scope === 'admin' ? adminTokenStore : userTokenStore;
  const token = scope !== 'public' ? store.get() : null;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method ?? 'GET',
    headers,
    credentials: 'include',
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get('content-type') ?? '';
  const data = contentType.includes('application/json') ? await res.json() : null;

  if (!res.ok) {
    const err = (data as ApiErrorShape | null)?.error;
    throw new ApiError(
      res.status,
      err?.code ?? 'unknown_error',
      err?.message ?? `HTTP ${res.status}`,
      err?.field_errors,
    );
  }

  return data as T;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  if (USE_MOCK_API) {
    return mockApi<T>(path, opts);
  }
  try {
    return await rawRequest<T>(path, opts);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && opts.scope !== 'public') {
      const refreshed = await refreshAccessToken(opts.scope ?? 'user');
      if (refreshed) {
        return await rawRequest<T>(path, opts);
      }
    }
    throw err;
  }
}

export const api = {
  get: <T>(path: string, opts: Omit<RequestOptions, 'method' | 'body'> = {}) =>
    apiRequest<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'method'> = {}) =>
    apiRequest<T>(path, { ...opts, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'method'> = {}) =>
    apiRequest<T>(path, { ...opts, method: 'PATCH', body }),
  delete: <T>(path: string, opts: Omit<RequestOptions, 'method' | 'body'> = {}) =>
    apiRequest<T>(path, { ...opts, method: 'DELETE' }),
};

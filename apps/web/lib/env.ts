// Публичные env-переменные для клиентского кода.
// NEXT_PUBLIC_USE_MOCK_API = 'true' → использовать mock ответы без реального backend.
// NEXT_PUBLIC_API_BASE_URL — база реального API (без trailing slash).

export const USE_MOCK_API =
  (process.env.NEXT_PUBLIC_USE_MOCK_API ?? 'true').toLowerCase() === 'true';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
);

export const API_PREFIX = '/api/v1';

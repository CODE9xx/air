// Публичные env-переменные для клиентского кода.
// NEXT_PUBLIC_USE_MOCK_API = 'true' → использовать mock ответы без реального backend.
// NEXT_PUBLIC_API_BASE_URL — база реального API (без trailing slash).
//
// NB: NEXT_PUBLIC_* читаются Next.js в момент `next build` и запекаются в
// клиентский бандл как литералы. Если build-stage контейнера не получает
// эти переменные (раньше так и было: docker compose env_file действует
// только в runtime), значения-фоллбеки окажутся в продовой сборке и
// перехватят реальные запросы через mock-слой. Поэтому:
//   * default for USE_MOCK_API = 'false' — безопасно для прода, включаем
//     mock только явным `NEXT_PUBLIC_USE_MOCK_API=true` в dev/storybook;
//   * build-args в deploy/docker-compose.prod.timeweb.yml + web.Dockerfile
//     прокидывают оба NEXT_PUBLIC_* в build-stage (см. Task #51.2).

export const USE_MOCK_API =
  (process.env.NEXT_PUBLIC_USE_MOCK_API ?? 'false').toLowerCase() === 'true';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
);

export const API_PREFIX = '/api/v1';

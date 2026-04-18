import createMiddleware from 'next-intl/middleware';
import { defaultLocale, locales } from './i18n/routing';

// Middleware: next-intl определяет локаль и редиректит / → /ru (или /en).
// Auth-check для /app и /admin делаем на клиенте в layout'ах (access токен в памяти).
export default createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always',
});

export const config = {
  // Исключаем API-роуты, статику, health.
  matcher: ['/((?!api|_next|_vercel|health|.*\\..*).*)'],
};

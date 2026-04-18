import createNextIntlPlugin from 'next-intl/plugin';

// next-intl читает request.ts из корня apps/web/i18n/request.ts.
const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // typedRoutes отключаем — он плохо дружит с динамическими [locale] сегментами.
    typedRoutes: false,
  },
  output: 'standalone',
};

export default withNextIntl(nextConfig);

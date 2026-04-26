import type { Metadata } from 'next';
import { getMarketingStaticPage } from '@/lib/marketingStaticPage';
import { StaticMarketingPage } from '@/components/marketing/StaticMarketingPage';

export const dynamic = 'force-static';

export const metadata: Metadata = {
  title: 'Тарифы CODE9',
  description:
    'Конструктор тарифа CODE9: сервер, AI-модули, токены, речевая аналитика, поддержка и скидки за 6 или 12 месяцев.',
};

export default function PricingPage({ params }: { params: { locale: string } }) {
  const page = getMarketingStaticPage('pricing', params.locale);

  return (
    <>
      <MarketingThemeScript />
      <StaticMarketingPage {...page} locale={params.locale} page="pricing" />
    </>
  );
}

function MarketingThemeScript() {
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `
          try {
            var theme = localStorage.getItem('code9-theme') || localStorage.getItem('code9_theme') || 'dark';
            document.documentElement.setAttribute('data-theme', theme);
            document.documentElement.classList.toggle('dark', theme === 'dark');
          } catch (_) {
            document.documentElement.setAttribute('data-theme', 'dark');
            document.documentElement.classList.add('dark');
          }
        `,
      }}
    />
  );
}

import type { Metadata } from 'next';
import { getMarketingStaticPage } from '@/lib/marketingStaticPage';
import { StaticMarketingPage } from '@/components/marketing/StaticMarketingPage';

export const dynamic = 'force-static';

export const metadata: Metadata = {
  title: 'CODE9 — AI-платформа для отдела продаж',
  description:
    'CODE9 подключается к amoCRM, строит дашборды, анализирует продажи, звонки, переписки и помогает отделу продаж работать быстрее.',
};

export default function LandingPage({ params }: { params: { locale: string } }) {
  const page = getMarketingStaticPage('landing', params.locale);

  return (
    <>
      <MarketingThemeScript />
      <StaticMarketingPage {...page} locale={params.locale} page="landing" />
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

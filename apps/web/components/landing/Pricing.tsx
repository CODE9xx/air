'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';

export function Pricing() {
  const t = useTranslations('landing.pricing');
  const locale = useLocale();
  return (
    <section id="pricing" className="container mx-auto py-20">
      <h2 className="text-3xl font-semibold text-center">{t('title')}</h2>
      <p className="mt-3 text-center text-muted-foreground max-w-2xl mx-auto">{t('subtitle')}</p>
      <div className="mt-10 grid md:grid-cols-3 gap-4 max-w-4xl mx-auto">
        {(['auditPrice', 'exportPrice', 'aiPrice'] as const).map((k) => (
          <div key={k} className="card p-6 text-center">
            <div className="text-lg font-semibold">{t(k)}</div>
          </div>
        ))}
      </div>
      <div className="mt-8 text-center">
        <Link
          href={`/${locale}/register`}
          className="inline-flex items-center px-5 py-3 rounded-md bg-primary text-white font-medium hover:bg-primary-700"
        >
          {t('ctaDeposit')}
        </Link>
      </div>
    </section>
  );
}

'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';

export function CTA() {
  const t = useTranslations('landing.cta');
  const locale = useLocale();
  return (
    <section className="bg-primary text-primary-foreground py-16">
      <div className="container mx-auto text-center">
        <h2 className="text-3xl font-semibold">{t('title')}</h2>
        <p className="mt-3 opacity-90">{t('subtitle')}</p>
        <Link
          href={`/${locale}/register`}
          className="mt-6 inline-flex items-center px-5 py-3 rounded-md bg-white text-primary font-medium hover:bg-muted"
        >
          {t('button')}
        </Link>
      </div>
    </section>
  );
}

'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';

export function Hero() {
  const t = useTranslations('landing.hero');
  const locale = useLocale();
  return (
    <section className="container mx-auto py-20 text-center">
      <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-foreground max-w-3xl mx-auto">
        {t('title')}
      </h1>
      <p className="mt-6 text-lg text-muted-foreground max-w-2xl mx-auto">{t('subtitle')}</p>
      <div className="mt-10 flex flex-wrap gap-3 justify-center">
        <Link
          href={`/${locale}/register`}
          className="inline-flex items-center px-5 py-3 rounded-md bg-primary text-white font-medium hover:bg-primary-700"
        >
          {t('ctaPrimary')}
        </Link>
        <a
          href="#features"
          className="inline-flex items-center px-5 py-3 rounded-md border border-border bg-white text-foreground font-medium hover:bg-muted"
        >
          {t('ctaSecondary')}
        </a>
      </div>
      <div className="mt-16 mx-auto max-w-4xl">
        <div className="rounded-xl border border-border bg-white shadow-soft p-6 text-left">
          <div className="grid grid-cols-3 gap-4 text-xs text-muted-foreground">
            <div className="h-2 rounded bg-primary/40" />
            <div className="h-2 rounded bg-primary/20" />
            <div className="h-2 rounded bg-primary/10" />
          </div>
          <div className="mt-4 h-32 grid grid-cols-5 items-end gap-2">
            {[60, 90, 45, 80, 120].map((h, i) => (
              <div
                key={i}
                className="rounded-md bg-gradient-to-t from-primary/20 to-primary/80"
                style={{ height: h }}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

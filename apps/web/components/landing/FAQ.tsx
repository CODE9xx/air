'use client';

import { useTranslations } from 'next-intl';

export function FAQ() {
  const t = useTranslations('landing.faq');
  return (
    <section id="faq" className="container mx-auto py-20">
      <h2 className="text-3xl font-semibold text-center mb-10">{t('title')}</h2>
      <div className="max-w-2xl mx-auto space-y-4">
        {([1, 2, 3] as const).map((i) => (
          <details key={i} className="card p-5 group">
            <summary className="cursor-pointer font-medium list-none flex items-center justify-between">
              <span>{t(`q${i}`)}</span>
              <span className="text-muted-foreground group-open:rotate-45 transition">+</span>
            </summary>
            <p className="mt-3 text-sm text-muted-foreground">{t(`a${i}`)}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

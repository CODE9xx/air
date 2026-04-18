'use client';

import { useTranslations } from 'next-intl';

export function Integrations() {
  const t = useTranslations('landing.integrations');
  const logos = ['amocrm', 'kommo', 'bitrix24', 'yookassa', 'stripe'] as const;
  return (
    <section id="integrations" className="bg-muted py-20">
      <div className="container mx-auto text-center">
        <h2 className="text-3xl font-semibold">{t('title')}</h2>
        <p className="mt-3 text-muted-foreground max-w-xl mx-auto">{t('subtitle')}</p>
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          {logos.map((l) => (
            <div
              key={l}
              className="px-5 py-3 rounded-md bg-white border border-border text-sm font-medium text-foreground shadow-soft"
            >
              {t(l)}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

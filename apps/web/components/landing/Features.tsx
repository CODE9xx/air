'use client';

import { useTranslations } from 'next-intl';
import { BarChart3, ClipboardCheck, Download, Sparkles } from 'lucide-react';

export function Features() {
  const t = useTranslations('landing.features');
  const items = [
    { key: 'audit', icon: <ClipboardCheck className="h-5 w-5" /> },
    { key: 'dashboards', icon: <BarChart3 className="h-5 w-5" /> },
    { key: 'export', icon: <Download className="h-5 w-5" /> },
    { key: 'ai', icon: <Sparkles className="h-5 w-5" /> },
  ] as const;
  return (
    <section id="features" className="container mx-auto py-20">
      <h2 className="text-3xl font-semibold text-center mb-12">{t('title')}</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        {items.map(({ key, icon }) => (
          <div key={key} className="card p-6">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
              {icon}
            </div>
            <h3 className="mt-4 text-base font-semibold">{t(`${key}.title`)}</h3>
            <p className="mt-2 text-sm text-muted-foreground">{t(`${key}.body`)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

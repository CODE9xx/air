'use client';

import { useTranslations } from 'next-intl';

export function Footer() {
  const t = useTranslations('footer');
  const tCommon = useTranslations('common');
  return (
    <footer className="border-t border-border bg-white">
      <div className="container mx-auto py-10 grid md:grid-cols-4 gap-6 text-sm">
        <div>
          <div className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-5 w-5 rounded bg-primary" />
            <span>{tCommon('brand')}</span>
          </div>
          <p className="mt-3 text-muted-foreground">{tCommon('tagline')}</p>
        </div>
        <div>
          <div className="font-medium mb-3">{t('legal')}</div>
          <ul className="space-y-2 text-muted-foreground">
            <li>{t('terms')}</li>
            <li>{t('privacy')}</li>
            <li>{t('dpa')}</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        {t('copyright', { year: new Date().getFullYear() })}
      </div>
    </footer>
  );
}

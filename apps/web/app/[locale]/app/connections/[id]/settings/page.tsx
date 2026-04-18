'use client';

import { useTranslations } from 'next-intl';

export default function ConnectionSettingsPage() {
  const t = useTranslations('cabinet.settings');
  const tCommon = useTranslations('common');
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="card p-6 text-sm text-muted-foreground">{tCommon('comingSoon')}</div>
    </div>
  );
}

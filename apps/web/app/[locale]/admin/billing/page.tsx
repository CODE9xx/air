'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/utils';

export default function AdminBillingPage() {
  const t = useTranslations('admin.billing');
  const locale = useLocale();
  const [data, setData] = useState<{ total_balance_cents: number; currency: string } | null>(null);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ total_balance_cents: number; currency: string }>('/admin/billing', {
        scope: 'admin',
      });
      setData(res);
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="card p-6">
        <div className="text-sm text-muted-foreground">{t('totalBalance')}</div>
        <div className="mt-1 text-3xl font-semibold">
          {data ? formatMoney(data.total_balance_cents, data.currency, locale) : '—'}
        </div>
      </div>
    </div>
  );
}

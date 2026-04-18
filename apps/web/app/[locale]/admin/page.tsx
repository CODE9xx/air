'use client';

import { useEffect, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/utils';

export default function AdminMetricsPage() {
  const t = useTranslations('admin.metrics');
  const locale = useLocale();
  const [billing, setBilling] = useState<{ total_balance_cents: number; currency: string } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<{ total_balance_cents: number; currency: string }>('/admin/billing', {
          scope: 'admin',
        });
        setBilling(res);
      } catch {
        setBilling({ total_balance_cents: 0, currency: 'RUB' });
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="grid md:grid-cols-4 gap-4">
        <Card label={t('totalWorkspaces')} value="2" />
        <Card label={t('activeConnections')} value="1" />
        <Card
          label={t('totalRevenue')}
          value={billing ? formatMoney(billing.total_balance_cents, billing.currency, locale) : '—'}
        />
        <Card label={t('jobsToday')} value="14" />
      </div>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

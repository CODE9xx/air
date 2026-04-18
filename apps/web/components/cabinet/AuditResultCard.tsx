'use client';

import { useTranslations } from 'next-intl';
import type { AuditResultSummary } from '@/lib/types';
import { formatNumber } from '@/lib/utils';

export function AuditResultCards({ summary, locale = 'ru' }: { summary: AuditResultSummary; locale?: string }) {
  const t = useTranslations('cabinet.audit');
  const items: Array<{ key: string; value: number }> = [
    { key: 'deals', value: summary.deals_count },
    { key: 'contacts', value: summary.contacts_count },
    { key: 'tasks', value: summary.tasks_count },
    { key: 'calls', value: summary.calls_count },
    { key: 'pipelines', value: summary.pipelines_count },
    { key: 'users', value: summary.users_count },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
      {items.map((i) => (
        <div key={i.key} className="card p-5">
          <div className="text-xs text-muted-foreground">{t(i.key)}</div>
          <div className="mt-1 text-2xl font-semibold">{formatNumber(i.value, locale)}</div>
        </div>
      ))}
    </div>
  );
}

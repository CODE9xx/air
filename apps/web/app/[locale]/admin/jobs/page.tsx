'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { Job } from '@/lib/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/utils';

export default function AdminJobsPage() {
  const t = useTranslations('admin.jobs');
  const locale = useLocale();
  const [items, setItems] = useState<Job[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: Job[] }>('/admin/jobs', { scope: 'admin' });
      setItems(res.items ?? []);
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      {items.length === 0 ? (
        <div className="card p-8 text-center text-muted-foreground text-sm">—</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2">id</th>
                <th className="px-4 py-2">{t('kind')}</th>
                <th className="px-4 py-2">{t('status')}</th>
                <th className="px-4 py-2">{t('startedAt')}</th>
                <th className="px-4 py-2">{t('finishedAt')}</th>
                <th className="px-4 py-2 text-right">{t('restart')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((j) => (
                <tr key={j.id} className="border-t border-border">
                  <td className="px-4 py-2 text-muted-foreground">{j.id}</td>
                  <td className="px-4 py-2 font-medium">{j.kind}</td>
                  <td className="px-4 py-2"><Badge>{j.status}</Badge></td>
                  <td className="px-4 py-2 text-muted-foreground">{formatDate(j.started_at, locale)}</td>
                  <td className="px-4 py-2 text-muted-foreground">{formatDate(j.finished_at, locale)}</td>
                  <td className="px-4 py-2 text-right">
                    <Button size="sm" variant="secondary">{t('restart')}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

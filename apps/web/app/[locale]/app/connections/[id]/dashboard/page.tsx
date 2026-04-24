'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { DashboardCharts } from '@/components/cabinet/DashboardCharts';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';
import type { DashboardOverview } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function ConnectionDashboardPage() {
  const t = useTranslations('cabinet.dashboard_page');
  const { user, ready } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    if (!wsId) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const res = await api.get<DashboardOverview>(`/workspaces/${wsId}/dashboards/overview`);
        setData(res);
      } finally {
        setLoading(false);
      }
    })();
  }, [ready, wsId]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      {loading && (
        <div className="grid lg:grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      )}
      {!loading && !data && <EmptyState title={t('noData')} />}
      {!loading && data && <DashboardCharts data={data} />}
    </div>
  );
}

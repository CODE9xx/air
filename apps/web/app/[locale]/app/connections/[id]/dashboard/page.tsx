'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { DashboardCharts } from '@/components/cabinet/DashboardCharts';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';
import type { DashboardOverview } from '@/lib/types';

type OverviewResponse = {
  total_deals: number;
  open_deals: number;
  won_deals: number;
  lost_deals: number;
};

type FunnelResponse = {
  stages: Array<{ stage: string; count: number; conversion_from_previous: number | null }>;
};

type ManagersResponse = {
  managers: Array<{
    user_id: string;
    full_name: string;
    deals_open: number;
    deals_won: number;
  }>;
};

type CallsResponse = { total: number };
type MessagesResponse = { total: number };

export default function ConnectionDashboardPage() {
  const t = useTranslations('cabinet.dashboard_page');
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [overview, funnel, managers, calls, messages] = await Promise.all([
          api.get<OverviewResponse>(`/crm/connections/${id}/dashboard/overview`),
          api.get<FunnelResponse>(`/crm/connections/${id}/dashboard/funnel`),
          api.get<ManagersResponse>(`/crm/connections/${id}/dashboard/managers`),
          api.get<CallsResponse>(`/crm/connections/${id}/dashboard/calls`),
          api.get<MessagesResponse>(`/crm/connections/${id}/dashboard/messages`),
        ]);
        setData({
          funnel: funnel.stages,
          conversions: {
            lead_to_deal: overview.total_deals > 0 ? 1 : 0,
            deal_to_won:
              overview.total_deals > 0 ? overview.won_deals / overview.total_deals : 0,
          },
          managers_activity: managers.managers.map((manager) => ({
            user_id: manager.user_id,
            name: manager.full_name,
            deals_open: manager.deals_open,
            deals_won: manager.deals_won,
          })),
          abandoned_deals: overview.lost_deals,
          total_calls: calls.total,
          total_messages: messages.total,
        });
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

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

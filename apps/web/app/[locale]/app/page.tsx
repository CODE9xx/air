'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { isCustomerVisibleCrmConnection } from '@/lib/connectionVisibility';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Skeleton } from '@/components/ui/Skeleton';

export default function CabinetHomePage() {
  const t = useTranslations('cabinet.dashboard');
  const locale = useLocale();
  const router = useRouter();
  const { user, ready } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;

  const [connections, setConnections] = useState<CrmConnection[] | null>(null);

  useEffect(() => {
    if (!ready) return;
    if (!wsId) {
      setConnections([]);
      return;
    }
    (async () => {
      try {
        const res = await api.get<CrmConnection[]>(`/workspaces/${wsId}/crm/connections`);
        setConnections(res.filter(isCustomerVisibleCrmConnection));
      } catch {
        setConnections([]);
      }
    })();
  }, [ready, wsId]);

  useEffect(() => {
    if (!ready || connections === null) return;

    const activeConnection =
      connections.find((connection) => connection.status === 'active') ?? connections[0] ?? null;

    router.replace(
      activeConnection
        ? `/${locale}/app/connections/${activeConnection.id}/dashboard`
        : `/${locale}/app/connections`,
    );
  }, [connections, locale, ready, router]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="grid md:grid-cols-3 gap-4">
        <StatCard label={t('activeConnections')} />
        <StatCard label={t('totalAudits')} />
        <StatCard label={t('totalCalls')} />
      </div>
    </div>
  );
}

function StatCard({ label }: { label: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <Skeleton className="h-8 w-16 mt-2" />
    </div>
  );
}

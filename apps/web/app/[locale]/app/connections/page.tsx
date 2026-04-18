'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { ConnectionCard } from '@/components/cabinet/ConnectionCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';

export default function ConnectionsPage() {
  const t = useTranslations('cabinet.connections');
  const locale = useLocale();
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';

  const [conns, setConns] = useState<CrmConnection[] | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<CrmConnection[]>(`/workspaces/${wsId}/crm/connections`);
        setConns(res);
      } catch {
        setConns([]);
      }
    })();
  }, [wsId]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <Link
          href={`/${locale}/app/connections/new`}
          className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
        >
          {t('addNew')}
        </Link>
      </header>

      {conns === null && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      )}

      {conns !== null && conns.length === 0 && (
        <EmptyState
          title={t('emptyTitle')}
          description={t('emptyBody')}
          action={
            <Link
              href={`/${locale}/app/connections/new`}
              className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
            >
              {t('addFirst')}
            </Link>
          }
        />
      )}

      {conns !== null && conns.length > 0 && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {conns.map((c) => (
            <ConnectionCard key={c.id} conn={c} />
          ))}
        </div>
      )}
    </div>
  );
}

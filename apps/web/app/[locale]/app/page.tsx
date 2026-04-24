'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Skeleton } from '@/components/ui/Skeleton';

export default function CabinetHomePage() {
  const t = useTranslations('cabinet.dashboard');
  const locale = useLocale();
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
        setConnections(res);
      } catch {
        setConnections([]);
      }
    })();
  }, [ready, wsId]);

  const active = (connections ?? []).filter((c) => c.status === 'active').length;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="grid md:grid-cols-3 gap-4">
        <StatCard label={t('activeConnections')} value={connections === null ? null : active} />
        <StatCard label={t('totalAudits')} value={connections === null ? null : 0} />
        <StatCard label={t('totalCalls')} value={connections === null ? null : 0} />
      </div>

      <section className="card p-6">
        <h2 className="text-lg font-semibold">{t('gettingStarted')}</h2>
        <ol className="mt-4 space-y-4 text-sm">
          {(['step1', 'step2', 'step3'] as const).map((s, idx) => (
            <li key={s} className="flex gap-3">
              <span className="inline-flex h-6 w-6 rounded-full bg-primary text-white text-xs items-center justify-center shrink-0">
                {idx + 1}
              </span>
              <div>
                <div className="font-medium">{t(s)}</div>
                <div className="text-muted-foreground">{t(`${s}Body` as `${typeof s}Body`)}</div>
              </div>
            </li>
          ))}
        </ol>
        <Link
          href={`/${locale}/app/connections/new`}
          className="mt-6 inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
        >
          {t('step1')}
        </Link>
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="card p-5">
      <div className="text-xs text-muted-foreground">{label}</div>
      {value === null ? <Skeleton className="h-8 w-16 mt-2" /> : <div className="mt-1 text-3xl font-semibold">{value}</div>}
    </div>
  );
}

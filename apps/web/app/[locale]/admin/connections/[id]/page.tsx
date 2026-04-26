'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { formatDate } from '@/lib/utils';

export default function AdminConnectionDetailPage() {
  const t = useTranslations('admin.connections');
  const tCommon = useTranslations('cabinet.connections');
  const locale = useLocale();
  const params = useParams<{ id: string }>();
  const [conn, setConn] = useState<CrmConnection | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    (async () => {
      try {
        const res = await api.get<CrmConnection>(`/admin/connections/${params.id}`, { scope: 'admin' });
        setConn(res);
      } catch {
        setConn(null);
      }
    })();
  }, [params]);

  if (!conn) return <div className="text-muted-foreground">…</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold capitalize">{t('title')}: {conn.provider}</h1>
      <div className="card p-5 grid md:grid-cols-2 gap-4 text-sm">
        <div><div className="text-xs text-muted-foreground">{t('provider')}</div><div className="mt-1 font-medium">{conn.provider}</div></div>
        <div><div className="text-xs text-muted-foreground">{t('status')}</div><div className="mt-1 font-medium">{conn.status}</div></div>
        <div><div className="text-xs text-muted-foreground">{tCommon('domain')}</div><div className="mt-1 font-medium">{conn.external_domain ?? '—'}</div></div>
        <div><div className="text-xs text-muted-foreground">{tCommon('lastSync')}</div><div className="mt-1 font-medium">{formatDate(conn.last_sync_at, locale)}</div></div>
      </div>
    </div>
  );
}

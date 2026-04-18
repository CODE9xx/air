'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatDate } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function ConnectionDetailPage() {
  const t = useTranslations('cabinet.connections');
  const tActions = useTranslations('cabinet.connections.actions');
  const tCommon = useTranslations('common');
  const params = useParams<{ id: string }>();
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';
  const id = params?.id;

  const [conn, setConn] = useState<CrmConnection | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const res = await api.get<CrmConnection>(`/crm/connections/${id}`);
        setConn(res);
      } catch {
        toast({ kind: 'error', title: tCommon('error') });
      } finally {
        setLoading(false);
      }
    })();
  }, [id, toast, tCommon]);

  const doPause = async () => {
    if (!conn) return;
    const next = conn.status === 'paused' ? 'resume' : 'pause';
    const res = await api.post<CrmConnection>(`/crm/connections/${conn.id}/${next}`);
    setConn(res);
  };

  const startTrialExport = async () => {
    if (!conn) return;
    try {
      await api.post(`/workspaces/${wsId}/export/jobs`, {
        crm_connection_id: conn.id,
        format: 'zip_csv_json',
        entities: ['deals'],
      });
      toast({ kind: 'success', title: tActions('trialExport') });
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
    }
  };

  if (loading) return <Skeleton className="h-40" />;
  if (!conn) return null;

  const statusKey = `status${conn.status.charAt(0).toUpperCase()}${conn.status.slice(1)}` as
    | 'statusActive' | 'statusPending' | 'statusPaused' | 'statusFailed' | 'statusDeleting' | 'statusDeleted';

  const tone = ({
    active: 'success', pending: 'info', paused: 'warning', failed: 'danger', deleting: 'warning', deleted: 'neutral',
  } as const)[conn.status] ?? 'neutral';

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold capitalize">{conn.provider}</h1>
          <div className="text-sm text-muted-foreground">{conn.external_domain}</div>
        </div>
        <Badge tone={tone}>{t(statusKey)}</Badge>
      </header>

      <div className="card p-5 grid md:grid-cols-3 gap-4 text-sm">
        <Field label={t('provider')} value={conn.provider} />
        <Field label={t('domain')} value={conn.external_domain ?? '—'} />
        <Field label={t('lastSync')} value={formatDate(conn.last_sync_at, locale)} />
        <Field label={t('tokenExpires')} value={formatDate(conn.token_expires_at, locale)} />
        <Field label={t('detail.createdAt')} value={formatDate(conn.created_at, locale)} />
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href={`/${locale}/app/connections/${conn.id}/audit`}
          className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
        >
          {tActions('runAudit')}
        </Link>
        <Button variant="secondary" onClick={startTrialExport}>{tActions('trialExport')}</Button>
        <Button variant="secondary" onClick={doPause}>
          {conn.status === 'paused' ? tActions('resume') : tActions('pause')}
        </Button>
        <Link href={`/${locale}/app/connections/${conn.id}/dashboard`} className="btn-secondary">
          {tActions('viewDashboard')}
        </Link>
        <Link href={`/${locale}/app/connections/${conn.id}/billing`} className="btn-secondary">
          {tActions('billing')}
        </Link>
        <Link href={`/${locale}/app/connections/${conn.id}/settings`} className="btn-secondary">
          {tActions('settings')}
        </Link>
        <Button variant="danger" onClick={() => router.push(`/${locale}/app/connections/${conn.id}/delete`)}>
          {tActions('delete')}
        </Button>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatDate } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';
import { useUserAuth } from '@/components/providers/AuthProvider';

/**
 * Флаги OAuth-колбэка, которые может присылать backend для конкретного connection.
 * См. apps/api/app/crm/oauth_router.py → `_ui_redirect(...)`.
 */
type OAuthFlash =
  | 'amocrm_connected'
  | 'amocrm_bad_referer'
  | 'amocrm_invalid_grant'
  | 'amocrm_exchange_failed'
  | 'amocrm_cancelled'
  | 'amocrm_credentials_missing'
  | 'mock_oauth_ok';

export default function ConnectionDetailPage() {
  const t = useTranslations('cabinet.connections');
  const tActions = useTranslations('cabinet.connections.actions');
  const tFlash = useTranslations('cabinet.connections.flash');
  const tCommon = useTranslations('common');
  const params = useParams<{ id: string }>();
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const { user } = useUserAuth();
  // Task #52.4 follow-up: НЕ подставляем синтетический 'ws-demo-1'.
  // wsId здесь нужен только для startTrialExport (POST /workspaces/{ws}/export/jobs).
  // Чтение connection-данных идёт через /crm/connections/{id} и от wsId не зависит,
  // поэтому страница рендерится корректно даже без workspace.
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const id = params?.id;

  const [conn, setConn] = useState<CrmConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const flashShown = useRef(false);

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

  // Показываем toast по OAuth-флагу и чистим query-string.
  useEffect(() => {
    if (flashShown.current) return;
    const flash = searchParams?.get('flash') as OAuthFlash | null;
    if (!flash) return;
    flashShown.current = true;
    const flashToKind: Record<OAuthFlash, 'success' | 'error' | 'info'> = {
      amocrm_connected: 'success',
      mock_oauth_ok: 'success',
      amocrm_cancelled: 'info',
      amocrm_bad_referer: 'error',
      amocrm_invalid_grant: 'error',
      amocrm_exchange_failed: 'error',
      amocrm_credentials_missing: 'error',
    };
    toast({
      kind: flashToKind[flash] ?? 'info',
      title: tFlash(flash),
    });
    const url = new URL(window.location.href);
    url.searchParams.delete('flash');
    router.replace(url.pathname + (url.search ? url.search : ''));
  }, [searchParams, toast, tFlash, router]);

  const doPause = async () => {
    if (!conn) return;
    const next = conn.status === 'paused' ? 'resume' : 'pause';
    const res = await api.post<CrmConnection>(`/crm/connections/${conn.id}/${next}`);
    setConn(res);
  };

  const startTrialExport = async () => {
    if (!conn) return;
    try {
      // Task #52.5: эндпойнт per-connection, не per-workspace.
      // Backend сам резолвит ownership через _get_conn_for_user → ставит
      // RQ job kind=build_export_zip с payload {connection_id, trial: true}.
      // Старый путь /workspaces/{ws}/export/jobs никогда не существовал
      // и всегда уходил в 404 → UI показывал toast «Ошибка».
      await api.post(`/crm/connections/${conn.id}/trial-export`);
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

  const amo = conn.metadata?.amo_account;
  const pullCounts = conn.metadata?.last_pull_counts ?? conn.metadata?.last_trial_export_counts;
  const pullCountsTitle = conn.metadata?.last_pull_counts
    ? t('detail.pullCounts')
    : t('detail.trialExportCounts');
  const lastPullAt = conn.metadata?.last_pull_at ?? conn.metadata?.last_trial_export_at ?? null;
  const lastPullAtLabel = conn.metadata?.last_pull_at
    ? t('detail.lastPullAt')
    : t('detail.lastTrialExportAt');
  const isMock = Boolean(conn.metadata?.mock);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold capitalize">
            {amo?.name ?? conn.name ?? conn.provider}
          </h1>
          <div className="text-sm text-muted-foreground">
            {amo?.subdomain ?? conn.external_domain ?? '—'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isMock && <Badge tone="neutral">{t('mockBadge')}</Badge>}
          <Badge tone={tone}>{t(statusKey)}</Badge>
        </div>
      </header>

      {conn.last_error && (
        <div className="card p-4 border-red-300 bg-red-50 dark:bg-red-950/30 text-sm text-red-700 dark:text-red-300">
          <div className="font-semibold">{t('lastError')}</div>
          <div className="mt-1 break-words">{conn.last_error}</div>
        </div>
      )}

      <div className="card p-5 grid md:grid-cols-3 gap-4 text-sm">
        <Field label={t('provider')} value={conn.provider} />
        <Field label={t('domain')} value={conn.external_domain ?? '—'} />
        <Field label={t('lastSync')} value={formatDate(conn.last_sync_at, locale)} />
        <Field label={t('tokenExpires')} value={formatDate(conn.token_expires_at, locale)} />
        <Field label={t('detail.createdAt')} value={formatDate(conn.created_at, locale)} />
        {lastPullAt && (
          <Field label={lastPullAtLabel} value={formatDate(lastPullAt, locale)} />
        )}
      </div>

      {amo && (amo.name || amo.subdomain || amo.country || amo.currency || amo.id != null) && (
        <section className="card p-5 text-sm space-y-3">
          <h2 className="text-lg font-semibold">{t('detail.amoAccount')}</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {amo.name && <Field label={t('detail.amoName')} value={amo.name} />}
            {amo.subdomain && (
              <Field label={t('detail.amoSubdomain')} value={amo.subdomain} />
            )}
            {amo.id != null && (
              <Field label={t('detail.amoId')} value={String(amo.id)} />
            )}
            {amo.country && <Field label={t('detail.amoCountry')} value={amo.country} />}
            {amo.currency && <Field label={t('detail.amoCurrency')} value={amo.currency} />}
          </div>
        </section>
      )}

      {pullCounts && (
        <section className="card p-5 text-sm space-y-3">
          <h2 className="text-lg font-semibold">{pullCountsTitle}</h2>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <CountField label={t('detail.pullPipelines')} value={pullCounts.pipelines} />
            <CountField label={t('detail.pullStages')} value={pullCounts.stages} />
            <CountField label={t('detail.pullUsers')} value={pullCounts.users} />
            <CountField label={t('detail.pullCompanies')} value={pullCounts.companies} />
            <CountField label={t('detail.pullContacts')} value={pullCounts.contacts} />
            <CountField label={t('detail.pullDeals')} value={pullCounts.deals} />
          </div>
        </section>
      )}

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

function CountField({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold text-lg tabular-nums">
        {typeof value === 'number' ? value.toLocaleString() : '—'}
      </div>
    </div>
  );
}

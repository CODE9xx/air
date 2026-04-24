'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { ApiError } from '@/lib/apiError';
import type { CrmConnection, FullExportTokenQuote, TokenEstimateResponse } from '@/lib/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatDate } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';

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

type ExportPreset = 'allTime' | 'last12Months' | 'currentYear' | 'custom';
type TokenEstimatePeriod = 'all_time' | 'active_export';

type ExportPipeline = {
  id: string;
  name: string;
  stages: Array<{ id: string; name: string; sort_order?: number | null }>;
};

type ExportOptions = {
  connection_id: string;
  pipelines: ExportPipeline[];
  source: string;
  empty_reason?: string | null;
};

type JobStatus = {
  id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string;
  error?: string | null;
  result?: {
    progress?: JobProgress;
  } | null;
};

type JobProgress = {
  stage?: string;
  completed_steps?: number;
  total_steps?: number;
  percent?: number;
  counts?: Record<string, number>;
  updated_at?: string;
};

function inputDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function defaultDateRange(preset: ExportPreset): { dateFrom: string; dateTo: string } {
  const now = new Date();
  if (preset === 'allTime') {
    return { dateFrom: '2000-01-01', dateTo: inputDate(now) };
  }
  if (preset === 'currentYear') {
    return { dateFrom: `${now.getFullYear()}-01-01`, dateTo: inputDate(now) };
  }
  const from = new Date(now);
  from.setFullYear(from.getFullYear() - 1);
  return { dateFrom: inputDate(from), dateTo: inputDate(now) };
}

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
  const id = params?.id;

  const [conn, setConn] = useState<CrmConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [showExportSetup, setShowExportSetup] = useState(false);
  const [exportOptions, setExportOptions] = useState<ExportOptions | null>(null);
  const [exportOptionsLoading, setExportOptionsLoading] = useState(false);
  const [exportPreset, setExportPreset] = useState<ExportPreset>('last12Months');
  const [dateFrom, setDateFrom] = useState(defaultDateRange('last12Months').dateFrom);
  const [dateTo, setDateTo] = useState(defaultDateRange('last12Months').dateTo);
  const [selectedPipelineIds, setSelectedPipelineIds] = useState<string[]>([]);
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportJobStatus, setExportJobStatus] = useState<string | null>(null);
  const [exportJobProgress, setExportJobProgress] = useState<JobProgress | null>(null);
  const [activeJobKind, setActiveJobKind] = useState<'export' | 'sync' | null>(null);
  const [exportRunning, setExportRunning] = useState(false);
  const [syncRunning, setSyncRunning] = useState(false);
  const [exportQuote, setExportQuote] = useState<FullExportTokenQuote | null>(null);
  const [exportQuoteLoading, setExportQuoteLoading] = useState(false);
  const [tokenEstimate, setTokenEstimate] = useState<TokenEstimateResponse | null>(null);
  const [tokenEstimateLoading, setTokenEstimateLoading] = useState(false);
  const [tokenEstimatePeriod, setTokenEstimatePeriod] = useState<TokenEstimatePeriod>('all_time');
  const [callHours, setCallHours] = useState('0');
  const flashShown = useRef(false);

  const reloadConnection = async () => {
    if (!id) return;
    const res = await api.get<CrmConnection>(`/crm/connections/${id}`);
    setConn(res);
  };

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        await reloadConnection();
      } catch {
        toast({ kind: 'error', title: tCommon('error') });
      } finally {
        setLoading(false);
      }
    })();
  }, [id, toast, tCommon]);

  useEffect(() => {
    if (!conn) return;
    (async () => {
      setTokenEstimateLoading(true);
      try {
        const estimate = await api.get<TokenEstimateResponse>(
          `/crm/connections/${conn.id}/token-estimate?period=${tokenEstimatePeriod}`,
        );
        setTokenEstimate(estimate);
      } catch {
        setTokenEstimate(null);
      } finally {
        setTokenEstimateLoading(false);
      }
    })();
  }, [conn?.id, tokenEstimatePeriod]);

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

  const openRealExportSetup = async () => {
    if (!conn) return;
    setShowExportSetup(true);
    if (exportOptions) return;
    setExportOptionsLoading(true);
    try {
      const options = await api.get<ExportOptions>(`/crm/connections/${conn.id}/export/options`);
      setExportOptions(options);
      setSelectedPipelineIds(options.pipelines.map((p) => p.id));
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
    } finally {
      setExportOptionsLoading(false);
    }
  };

  const applyPreset = (preset: ExportPreset) => {
    setExportPreset(preset);
    if (preset === 'custom') return;
    const next = defaultDateRange(preset);
    setDateFrom(next.dateFrom);
    setDateTo(next.dateTo);
  };

  const togglePipeline = (pipelineId: string) => {
    setSelectedPipelineIds((current) =>
      current.includes(pipelineId)
        ? current.filter((id) => id !== pipelineId)
        : [...current, pipelineId],
    );
  };

  useEffect(() => {
    if (!showExportSetup || !conn || !dateFrom || !dateTo) return;
    const timer = window.setTimeout(async () => {
      setExportQuoteLoading(true);
      try {
        const quote = await api.post<FullExportTokenQuote>(
          `/crm/connections/${conn.id}/full-export/quote`,
          {
            date_from: dateFrom,
            date_to: dateTo,
            pipeline_ids: selectedPipelineIds,
          },
        );
        setExportQuote(quote);
      } catch {
        setExportQuote(null);
      } finally {
        setExportQuoteLoading(false);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [showExportSetup, conn?.id, dateFrom, dateTo, selectedPipelineIds.join('|')]);

  const startRealExport = async () => {
    if (!conn) return;
    setExportRunning(true);
    try {
      const quote = await api.post<FullExportTokenQuote>(
        `/crm/connections/${conn.id}/full-export/quote`,
        {
          date_from: dateFrom,
          date_to: dateTo,
          pipeline_ids: selectedPipelineIds,
        },
      );
      setExportQuote(quote);
      if (!quote.can_start) {
        toast({
          kind: 'warning',
          title: `Не хватает ${quote.missing_tokens.toLocaleString()} AIC9-токенов`,
        });
        setExportRunning(false);
        return;
      }
      const res = await api.post<{ job_id: string }>(
        `/crm/connections/${conn.id}/full-export`,
        {
          date_from: dateFrom,
          date_to: dateTo,
          pipeline_ids: selectedPipelineIds,
        },
      );
      setExportJobId(res.job_id);
      setExportJobStatus('queued');
      setExportJobProgress(null);
      setActiveJobKind('export');
      toast({ kind: 'success', title: tActions('realExportStarted') });
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
      setExportRunning(false);
    }
  };

  const startIncrementalSync = async () => {
    if (!conn) return;
    setSyncRunning(true);
    try {
      const res = await api.post<{ job_id: string }>(`/crm/connections/${conn.id}/sync`);
      setExportJobId(res.job_id);
      setExportJobStatus('queued');
      setExportJobProgress(null);
      setActiveJobKind('sync');
      toast({ kind: 'success', title: tActions('syncStarted') });
    } catch (error) {
      if (error instanceof ApiError && error.code === 'sync_already_running') {
        toast({ kind: 'info', title: tActions('syncAlreadyRunning') });
      } else {
        toast({ kind: 'error', title: tCommon('error') });
      }
      setSyncRunning(false);
    }
  };

  useEffect(() => {
    if (!exportJobId) return;
    const timer = window.setInterval(async () => {
      try {
        const job = await api.get<JobStatus>(`/jobs/${exportJobId}`);
        setExportJobStatus(job.status);
        setExportJobProgress(job.result?.progress ?? null);
        if (job.status === 'succeeded') {
          window.clearInterval(timer);
          setExportRunning(false);
          setSyncRunning(false);
          await reloadConnection();
          toast({
            kind: 'success',
            title: activeJobKind === 'sync' ? tActions('syncDone') : tActions('realExportDone'),
          });
        }
        if (job.status === 'failed') {
          window.clearInterval(timer);
          setExportRunning(false);
          setSyncRunning(false);
          toast({ kind: 'error', title: job.error ?? tCommon('error') });
        }
      } catch {
        window.clearInterval(timer);
        setExportRunning(false);
        setSyncRunning(false);
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [exportJobId, activeJobKind, tActions, tCommon, toast]);

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
  const activeExport = conn.metadata?.active_export;
  const sync = conn.sync;
  const normalizedCallHours = Number.parseFloat(callHours.replace(',', '.'));
  const callMinutes = Number.isFinite(normalizedCallHours)
    ? Math.max(0, Math.round(normalizedCallHours * 60))
    : 0;
  const callTokensLow = tokenEstimate
    ? callMinutes * tokenEstimate.calls.tokens_per_minute_low
    : 0;
  const callTokensHigh = tokenEstimate
    ? callMinutes * tokenEstimate.calls.tokens_per_minute_high
    : 0;
  const totalWithCallsLow = tokenEstimate
    ? tokenEstimate.total_tokens_without_calls + callTokensLow
    : 0;
  const totalWithCallsHigh = tokenEstimate
    ? tokenEstimate.total_tokens_without_calls + callTokensHigh
    : 0;

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

      {activeExport && (
        <section className="card p-5 text-sm space-y-3">
          <h2 className="text-lg font-semibold">{t('detail.activeExport')}</h2>
          <div className="grid md:grid-cols-4 gap-4">
            <Field label={t('detail.exportDateBasis')} value={t('detail.createdAtBasis')} />
            <Field label={t('detail.exportDateFrom')} value={activeExport.date_from ?? '—'} />
            <Field label={t('detail.exportDateTo')} value={activeExport.date_to ?? '—'} />
            <Field
              label={t('detail.exportPipelines')}
              value={
                activeExport.pipeline_ids && activeExport.pipeline_ids.length > 0
                  ? String(activeExport.pipeline_ids.length)
                  : t('detail.allPipelines')
              }
            />
          </div>
        </section>
      )}

      {sync && (
        <section className="card p-5 text-sm space-y-3">
          <h2 className="text-lg font-semibold">Автообновление данных</h2>
          <div className="grid md:grid-cols-4 gap-4">
            <Field label="Режим" value="Догрузка изменений" />
            <Field label="Тариф" value={sync.plan_key ?? 'free'} />
            <Field label="Частота" value={formatCadence(sync.cadence_seconds)} />
            <Field label="Следующее обновление" value={formatDate(sync.next_auto_sync_at, locale)} />
          </div>
        </section>
      )}

      <section className="card p-5 text-sm space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">{t('detail.tokenEstimateTitle')}</h2>
            {tokenEstimate && (
              <div className="mt-1 text-xs text-muted-foreground">
                {t('detail.tokenEstimateSource')}:{' '}
                {tokenEstimate.basis === 'full_database_snapshot'
                  ? t('detail.full_database_snapshot')
                  : tokenEstimate.basis === 'active_export_scaled'
                    ? t('detail.active_export_scaled')
                    : t('detail.active_export_lower_bound')}
              </div>
            )}
          </div>
          {tokenEstimate?.captured_at && (
            <Badge tone="info">{formatDate(tokenEstimate.captured_at, locale)}</Badge>
          )}
        </div>

        {tokenEstimateLoading && <Skeleton className="h-24" />}

        {tokenEstimate && (
          <>
            <div className="flex flex-wrap gap-2">
              {(['all_time', 'active_export'] as TokenEstimatePeriod[]).map((period) => (
                <Button
                  key={period}
                  type="button"
                  size="sm"
                  variant={tokenEstimatePeriod === period ? 'primary' : 'secondary'}
                  onClick={() => setTokenEstimatePeriod(period)}
                >
                  {period === 'all_time'
                    ? t('detail.tokenEstimateAllTime')
                    : t('detail.tokenEstimateActiveExport')}
                </Button>
              ))}
            </div>
            {(tokenEstimate.date_from || tokenEstimate.date_to) && (
              <div className="text-xs text-muted-foreground">
                {tokenEstimate.date_from ?? '—'} – {tokenEstimate.date_to ?? '—'}
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {tokenEstimate.items.map((item) => (
                <div key={item.key} className="rounded-md border border-border p-3">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className="mt-1 font-semibold tabular-nums">
                    {item.count.toLocaleString()}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {formatCompactTokens(item.estimated_tokens)}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid md:grid-cols-3 gap-3">
              <CountField
                label={t('detail.tokensWithoutCalls')}
                value={tokenEstimate.total_tokens_without_calls}
              />
              <label className="block">
                <span className="text-xs text-muted-foreground">{t('detail.callHours')}</span>
                <input
                  className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
                  min="0"
                  step="0.5"
                  type="number"
                  value={callHours}
                  onChange={(event) => setCallHours(event.target.value)}
                />
              </label>
              <div>
                <div className="text-xs text-muted-foreground">
                  {t('detail.tokensWithCalls')}
                </div>
                <div className="mt-1 font-semibold text-lg tabular-nums">
                  {formatCompactTokens(totalWithCallsLow)} – {formatCompactTokens(totalWithCallsHigh)}
                </div>
              </div>
            </div>

            <div className="rounded-md border border-border bg-muted p-3 text-xs text-muted-foreground">
              {t('detail.callEstimateHint', {
                low: tokenEstimate.calls.tokens_per_minute_low,
                high: tokenEstimate.calls.tokens_per_minute_high,
              })}
            </div>
          </>
        )}
      </section>

      {showExportSetup && (
        <section className="card p-5 text-sm space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="text-lg font-semibold">{t('detail.realExportTitle')}</h2>
            {exportJobStatus && (
              <Badge tone={exportJobStatus === 'failed' ? 'danger' : exportJobStatus === 'succeeded' ? 'success' : 'info'}>
                {exportJobStatus}
              </Badge>
            )}
          </div>
          {exportJobProgress && (
            <div className="rounded-md border border-border bg-muted p-3">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span>Этап: {formatJobStage(exportJobProgress.stage)}</span>
                <span className="font-semibold tabular-nums">
                  {typeof exportJobProgress.percent === 'number'
                    ? `${exportJobProgress.percent}%`
                    : '—'}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-white">
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, exportJobProgress.percent ?? 0))}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {(['allTime', 'last12Months', 'currentYear', 'custom'] as ExportPreset[]).map((preset) => (
              <Button
                key={preset}
                type="button"
                size="sm"
                variant={exportPreset === preset ? 'primary' : 'secondary'}
                onClick={() => applyPreset(preset)}
              >
                {t(`detail.${preset}`)}
              </Button>
            ))}
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-muted-foreground">{t('detail.exportDateFrom')}</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
                type="date"
                value={dateFrom}
                onChange={(event) => {
                  setExportPreset('custom');
                  setDateFrom(event.target.value);
                }}
              />
            </label>
            <label className="block">
              <span className="text-xs text-muted-foreground">{t('detail.exportDateTo')}</span>
              <input
                className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
                type="date"
                value={dateTo}
                onChange={(event) => {
                  setExportPreset('custom');
                  setDateTo(event.target.value);
                }}
              />
            </label>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">{t('detail.exportPipelines')}</div>
              {exportOptions && exportOptions.pipelines.length > 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelectedPipelineIds(exportOptions.pipelines.map((p) => p.id))}
                >
                  {t('detail.selectAllPipelines')}
                </Button>
              )}
            </div>
            {exportOptionsLoading && <Skeleton className="h-12" />}
            {exportOptions && exportOptions.pipelines.length === 0 && (
              <div className="rounded-md border border-border bg-muted p-3 text-muted-foreground">
                {t('detail.allPipelines')}
              </div>
            )}
            {exportOptions && exportOptions.pipelines.length > 0 && (
              <div className="grid md:grid-cols-2 gap-2">
                {exportOptions.pipelines.map((pipeline) => (
                  <label
                    key={pipeline.id}
                    className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
                  >
                    <span className="truncate">{pipeline.name}</span>
                    <input
                      type="checkbox"
                      checked={selectedPipelineIds.includes(pipeline.id)}
                      onChange={() => togglePipeline(pipeline.id)}
                    />
                  </label>
                ))}
              </div>
            )}
          </div>
          {exportQuoteLoading && <Skeleton className="h-24" />}
          {exportQuote && (
            <div className="rounded-md border border-border bg-muted p-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <CountField label="Клиентов в расчёте" value={exportQuote.estimated_contacts} />
                <CountField label="Нужно токенов" value={exportQuote.estimated_tokens} />
                <CountField label="Доступно токенов" value={exportQuote.available_tokens} />
                <CountField label="Не хватает" value={exportQuote.missing_tokens} />
              </div>
              <div className="mt-3 flex items-center justify-between gap-3 flex-wrap text-sm">
                <div className={exportQuote.can_start ? 'text-success' : 'text-danger'}>
                  {exportQuote.can_start
                    ? 'Токенов хватает, можно запускать выгрузку.'
                    : `Недостаточно токенов для выгрузки за выбранный период.`}
                </div>
                {!exportQuote.can_start && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => router.push(`/${locale}/app/connections/${conn.id}/billing`)}
                  >
                    Пополнить баланс
                  </Button>
                )}
              </div>
            </div>
          )}
          <Button
            onClick={startRealExport}
            loading={exportRunning}
            disabled={exportQuoteLoading || (exportQuote ? !exportQuote.can_start : false)}
          >
            {tActions('startRealExport')}
          </Button>
        </section>
      )}

      <div className="flex flex-wrap gap-2">
        <Link
          href={`/${locale}/app/connections/${conn.id}/audit`}
          className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
        >
          {tActions('runAudit')}
        </Link>
        <Button variant="secondary" onClick={openRealExportSetup}>{tActions('configureRealExport')}</Button>
        <Button
          variant="secondary"
          onClick={startIncrementalSync}
          loading={syncRunning}
          disabled={exportRunning || syncRunning}
        >
          {tActions('syncNow')}
        </Button>
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

function formatCompactTokens(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}

function formatCadence(seconds: number | undefined): string {
  if (!seconds) return '—';
  if (seconds <= 15 * 60) return 'каждые 15 минут';
  if (seconds <= 60 * 60) return 'каждый час';
  if (seconds <= 24 * 60 * 60) return 'раз в день';
  return `раз в ${Math.round(seconds / 3600)} ч`;
}

function formatJobStage(stage: string | undefined): string {
  const labels: Record<string, string> = {
    pipelines: 'воронки',
    stages: 'этапы',
    users: 'пользователи',
    companies: 'компании',
    contacts: 'контакты',
    deals: 'сделки',
  };
  return stage ? labels[stage] ?? stage : 'ожидание';
}

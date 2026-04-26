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
  kind?: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string;
  error?: string | null;
  queue_position?: number | null;
  jobs_ahead?: number | null;
  queue_length?: number | null;
  estimated_wait_seconds?: number | null;
  estimated_duration_seconds?: number | null;
  estimated_remaining_seconds?: number | null;
  estimated_records?: number | null;
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
  const [exportJobMeta, setExportJobMeta] = useState<JobStatus | null>(null);
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

  const loadExportOptions = async (resetSelection = false) => {
    if (!conn) return null;
    setExportOptionsLoading(true);
    try {
      const options = await api.get<ExportOptions>(`/crm/connections/${conn.id}/export/options`);
      setExportOptions(options);
      setSelectedPipelineIds((current) => {
        const nextIds = options.pipelines.map((p) => p.id);
        if (resetSelection || current.length === 0) return nextIds;
        return current.filter((id) => nextIds.includes(id));
      });
      return options;
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
      return null;
    } finally {
      setExportOptionsLoading(false);
    }
  };

  const attachActivePullJob = async () => {
    if (!conn) return false;
    const jobs = await api.get<JobStatus[]>(`/crm/connections/${conn.id}/jobs`);
    const activeJob = jobs.find(
      (job) =>
        job.kind === 'pull_amocrm_core' &&
        (job.status === 'queued' || job.status === 'running'),
    );
    if (!activeJob) return false;
    setExportJobId(activeJob.id);
    setExportJobStatus(activeJob.status);
    setExportJobProgress(activeJob.result?.progress ?? null);
    setExportJobMeta(activeJob);
    setActiveJobKind('sync');
    setSyncRunning(true);
    return true;
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
    if (exportOptions?.pipelines.length) return;
    await loadExportOptions(true);
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
          title: connectionDetailText(locale, 'missingTokensToast', {
            tokens: quote.missing_tokens.toLocaleString(),
          }),
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
      setExportJobMeta(null);
      setActiveJobKind('export');
      toast({ kind: 'success', title: tActions('realExportStarted') });
    } catch (error) {
      if (error instanceof ApiError && error.code === 'sync_already_running') {
        try {
          await attachActivePullJob();
        } catch {
          // The conflict itself is enough to explain the state to the user.
        }
        toast({ kind: 'info', title: tActions('syncAlreadyRunning') });
      } else {
        toast({ kind: 'error', title: tCommon('error') });
      }
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
      setExportJobMeta(null);
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
        setExportJobMeta(job);
        if (job.status === 'succeeded') {
          window.clearInterval(timer);
          setExportRunning(false);
          setSyncRunning(false);
          await reloadConnection();
          if (showExportSetup) {
            await loadExportOptions(exportOptions?.pipelines.length === 0);
          }
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
            {'tasks' in pullCounts && <CountField label={formatProgressCountLabel('tasks', locale)} value={Number(pullCounts.tasks ?? 0)} />}
            {'notes' in pullCounts && <CountField label={formatProgressCountLabel('notes', locale)} value={Number(pullCounts.notes ?? 0)} />}
            {'calls' in pullCounts && <CountField label={formatProgressCountLabel('calls', locale)} value={Number(pullCounts.calls ?? 0)} />}
            {'chats' in pullCounts && <CountField label={formatProgressCountLabel('chats', locale)} value={Number(pullCounts.chats ?? 0)} />}
            {'messages' in pullCounts && <CountField label={formatProgressCountLabel('messages', locale)} value={Number(pullCounts.messages ?? 0)} />}
            {'events' in pullCounts && <CountField label={formatProgressCountLabel('events', locale)} value={Number(pullCounts.events ?? 0)} />}
            {'tags' in pullCounts && <CountField label={formatProgressCountLabel('tags', locale)} value={Number(pullCounts.tags ?? 0)} />}
            {'products' in pullCounts && <CountField label={formatProgressCountLabel('products', locale)} value={Number(pullCounts.products ?? 0)} />}
            {'deal_products' in pullCounts && <CountField label={formatProgressCountLabel('deal_products', locale)} value={Number(pullCounts.deal_products ?? 0)} />}
            {'deal_contacts' in pullCounts && <CountField label={formatProgressCountLabel('deal_contacts', locale)} value={Number(pullCounts.deal_contacts ?? 0)} />}
            {'deal_companies' in pullCounts && <CountField label={formatProgressCountLabel('deal_companies', locale)} value={Number(pullCounts.deal_companies ?? 0)} />}
            {'stage_transitions' in pullCounts && <CountField label={formatProgressCountLabel('stage_transitions', locale)} value={Number(pullCounts.stage_transitions ?? 0)} />}
            {'deal_sources' in pullCounts && <CountField label={formatProgressCountLabel('deal_sources', locale)} value={Number(pullCounts.deal_sources ?? 0)} />}
            {'custom_fields' in pullCounts && <CountField label={formatProgressCountLabel('custom_fields', locale)} value={Number(pullCounts.custom_fields ?? 0)} />}
            {'custom_field_values' in pullCounts && <CountField label={formatProgressCountLabel('custom_field_values', locale)} value={Number(pullCounts.custom_field_values ?? 0)} />}
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
          {activeExport.messages_coverage && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-300">
              {formatMessagesCoverage(activeExport.messages_coverage, locale)}
            </div>
          )}
        </section>
      )}

      {sync && (
        <section className="card p-5 text-sm space-y-3">
          <h2 className="text-lg font-semibold">{connectionDetailText(locale, 'autoUpdateTitle')}</h2>
          <div className="grid md:grid-cols-4 gap-4">
            <Field label={connectionDetailText(locale, 'mode')} value={connectionDetailText(locale, 'incrementalMode')} />
            <Field label={connectionDetailText(locale, 'plan')} value={sync.plan_key ?? 'free'} />
            <Field label={connectionDetailText(locale, 'cadence')} value={formatCadence(sync.cadence_seconds, locale)} />
            <Field label={connectionDetailText(locale, 'nextUpdate')} value={formatDate(sync.next_auto_sync_at, locale)} />
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
          {(exportJobProgress || exportJobMeta) && (
            <div className="rounded-md border border-border bg-muted p-3">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span>{connectionDetailText(locale, 'stage')}: {formatJobStage(exportJobProgress?.stage, locale)}</span>
                <span className="font-semibold tabular-nums">
                  {typeof exportJobProgress?.percent === 'number'
                    ? `${exportJobProgress.percent}%`
                    : '—'}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-white">
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, exportJobProgress?.percent ?? 0))}%` }}
                />
              </div>
              <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                {typeof exportJobMeta?.queue_position === 'number' && (
                  <div>
                    {connectionDetailText(locale, 'queuePosition')}: <span className="font-medium text-foreground">#{exportJobMeta.queue_position}</span>
                  </div>
                )}
                {typeof exportJobMeta?.estimated_remaining_seconds === 'number' && (
                  <div>
                    {connectionDetailText(locale, 'timeLeft')}: <span className="font-medium text-foreground">{formatDuration(exportJobMeta.estimated_remaining_seconds, locale)}</span>
                  </div>
                )}
                {typeof exportJobMeta?.estimated_records === 'number' && (
                  <div>
                    {connectionDetailText(locale, 'estimatedRecords')}: <span className="font-medium text-foreground">{exportJobMeta.estimated_records.toLocaleString()}</span>
                  </div>
                )}
              </div>
              {exportJobProgress?.counts && Object.keys(exportJobProgress.counts).length > 0 && (
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {Object.entries(exportJobProgress.counts).map(([key, value]) => (
                    <div key={key} className="rounded-md border border-border bg-white px-2 py-1.5">
                      <div className="text-[11px] text-muted-foreground">{formatProgressCountLabel(key, locale)}</div>
                      <div className="font-semibold tabular-nums text-foreground">{Number(value || 0).toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              )}
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
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-sm">
                <CountField label={connectionDetailText(locale, 'clientsInQuote')} value={exportQuote.estimated_contacts} />
                <CountField label={connectionDetailText(locale, 'recordsInQuote')} value={exportQuote.estimated_records} />
                <CountField label={connectionDetailText(locale, 'estimatedTime')} value={undefined} textValue={formatDuration(exportQuote.estimated_duration_seconds ?? 0, locale)} />
                <CountField label={connectionDetailText(locale, 'tokensNeeded')} value={exportQuote.estimated_tokens} />
                <CountField label={connectionDetailText(locale, 'tokensAvailable')} value={exportQuote.available_tokens} />
                <CountField label={connectionDetailText(locale, 'tokensMissing')} value={exportQuote.missing_tokens} />
              </div>
              <div className="mt-3 flex items-center justify-between gap-3 flex-wrap text-sm">
                <div className={exportQuote.can_start ? 'text-success' : 'text-danger'}>
                  {exportQuote.can_start
                    ? connectionDetailText(locale, 'tokensEnough')
                    : connectionDetailText(locale, 'tokensNotEnough')}
                </div>
                {!exportQuote.can_start && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => router.push(`/${locale}/app/connections/${conn.id}/billing`)}
                  >
                    {connectionDetailText(locale, 'topUpBalance')}
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

function CountField({ label, value, textValue }: { label: string; value: number | undefined; textValue?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold text-lg tabular-nums">
        {textValue ?? (typeof value === 'number' ? value.toLocaleString() : '—')}
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

function formatDuration(seconds: number, locale: string): string {
  if (!seconds || seconds < 0) return '—';
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) {
    if (locale === 'en') return `${minutes} min`;
    if (locale === 'es') return `${minutes} min`;
    return `${minutes} мин`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (rest === 0) {
    if (locale === 'en') return `${hours} h`;
    if (locale === 'es') return `${hours} h`;
    return `${hours} ч`;
  }
  if (locale === 'en') return `${hours} h ${rest} min`;
  if (locale === 'es') return `${hours} h ${rest} min`;
  return `${hours} ч ${rest} мин`;
}

function formatCadence(seconds: number | undefined, locale: string): string {
  if (!seconds) return '—';
  if (locale === 'en') {
    if (seconds <= 15 * 60) return 'every 15 minutes';
    if (seconds <= 60 * 60) return 'hourly';
    if (seconds <= 24 * 60 * 60) return 'daily';
    return `every ${Math.round(seconds / 3600)} h`;
  }
  if (locale === 'es') {
    if (seconds <= 15 * 60) return 'cada 15 minutos';
    if (seconds <= 60 * 60) return 'cada hora';
    if (seconds <= 24 * 60 * 60) return 'una vez al día';
    return `cada ${Math.round(seconds / 3600)} h`;
  }
  if (seconds <= 15 * 60) return 'каждые 15 минут';
  if (seconds <= 60 * 60) return 'каждый час';
  if (seconds <= 24 * 60 * 60) return 'раз в день';
  return `раз в ${Math.round(seconds / 3600)} ч`;
}

function formatProgressCountLabel(key: string, locale: string): string {
  const labelsByLocale: Record<string, Record<string, string>> = {
    ru: {
      pipelines: 'Воронки',
      stages: 'Этапы',
      users: 'Менеджеры',
      companies: 'Компании',
      companies_imported: 'Компании сейчас',
      contacts: 'Контакты',
      contacts_imported: 'Контакты сейчас',
      deals: 'Сделки',
      deals_processed: 'Сделки обработано',
      deals_imported: 'Сделки сейчас',
      tags: 'Теги',
      products: 'Товары/услуги',
      products_imported: 'Товары сейчас',
      products_processed: 'Товары обработано',
      deal_products: 'Товары в сделках',
      deal_products_linked: 'Связи товаров обновлено',
      tasks: 'Задачи',
      tasks_imported: 'Задачи сейчас',
      tasks_processed: 'Задачи обработано',
      notes: 'События/notes',
      notes_imported: 'Notes сейчас',
      notes_processed: 'Notes обработано',
      calls: 'Звонки',
      calls_processed: 'Звонки обработано',
      chats: 'Чаты',
      chats_processed: 'Чаты обработано',
      messages: 'Сообщения',
      messages_imported: 'Сообщения сейчас',
      messages_processed: 'Сообщения обработано',
      messages_chats_seen: 'Чатов найдено',
      messages_chats_matched: 'Чатов связано',
      messages_unmatched_chats: 'Чатов без связи',
      events: 'События',
      events_imported: 'События сейчас',
      events_processed: 'События обработано',
      contacts_scope: 'Контакты в выбранных воронках',
      selected_deals: 'Сделок в срезе',
      selected_contacts: 'Контактов в срезе',
      deal_contacts: 'Связи сделка-контакт',
      deal_companies: 'Связи сделка-компания',
      stage_transitions: 'Переходы этапов',
      stage_transitions_processed: 'Переходы обработано',
      deal_sources: 'Источники сделок',
      custom_fields: 'Поля amoCRM',
      custom_fields_imported: 'Поля сейчас',
      custom_fields_processed: 'Поля обработано',
      custom_field_values: 'Значения полей',
      sources: 'Источники',
      tasks_enriched: 'Задачи расширенно',
    },
    en: {
      pipelines: 'Pipelines',
      stages: 'Stages',
      users: 'Managers',
      companies: 'Companies',
      companies_imported: 'Companies now',
      contacts: 'Contacts',
      contacts_imported: 'Contacts now',
      deals: 'Deals',
      deals_processed: 'Deals processed',
      deals_imported: 'Deals now',
      tags: 'Tags',
      products: 'Products/services',
      products_imported: 'Products now',
      products_processed: 'Products processed',
      deal_products: 'Deal products',
      deal_products_linked: 'Product links updated',
      tasks: 'Tasks',
      tasks_imported: 'Tasks now',
      tasks_processed: 'Tasks processed',
      notes: 'Events/notes',
      notes_imported: 'Notes now',
      notes_processed: 'Notes processed',
      calls: 'Calls',
      calls_processed: 'Calls processed',
      chats: 'Chats',
      chats_processed: 'Chats processed',
      messages: 'Messages',
      messages_imported: 'Messages now',
      messages_processed: 'Messages processed',
      messages_chats_seen: 'Chats seen',
      messages_chats_matched: 'Chats matched',
      messages_unmatched_chats: 'Unmatched chats',
      events: 'Events',
      events_imported: 'Events now',
      events_processed: 'Events processed',
      contacts_scope: 'Contacts in selected pipelines',
      selected_deals: 'Deals in scope',
      selected_contacts: 'Contacts in scope',
      deal_contacts: 'Deal-contact links',
      deal_companies: 'Deal-company links',
      stage_transitions: 'Stage transitions',
      stage_transitions_processed: 'Transitions processed',
      deal_sources: 'Deal sources',
      custom_fields: 'amoCRM fields',
      custom_fields_imported: 'Fields now',
      custom_fields_processed: 'Fields processed',
      custom_field_values: 'Field values',
      sources: 'Sources',
      tasks_enriched: 'Enriched tasks',
    },
    es: {
      pipelines: 'Embudos',
      stages: 'Etapas',
      users: 'Gerentes',
      companies: 'Compañías',
      companies_imported: 'Compañías ahora',
      contacts: 'Contactos',
      contacts_imported: 'Contactos ahora',
      deals: 'Deals',
      deals_processed: 'Deals procesados',
      deals_imported: 'Deals ahora',
      tags: 'Etiquetas',
      products: 'Productos/servicios',
      products_imported: 'Productos ahora',
      products_processed: 'Productos procesados',
      deal_products: 'Productos en deals',
      deal_products_linked: 'Vínculos actualizados',
      tasks: 'Tareas',
      tasks_imported: 'Tareas ahora',
      tasks_processed: 'Tareas procesadas',
      notes: 'Eventos/notas',
      notes_imported: 'Notas ahora',
      notes_processed: 'Notas procesadas',
      calls: 'Llamadas',
      calls_processed: 'Llamadas procesadas',
      chats: 'Chats',
      chats_processed: 'Chats procesados',
      messages: 'Mensajes',
      messages_imported: 'Mensajes ahora',
      messages_processed: 'Mensajes procesados',
      messages_chats_seen: 'Chats encontrados',
      messages_chats_matched: 'Chats vinculados',
      messages_unmatched_chats: 'Chats sin vínculo',
      events: 'Eventos',
      events_imported: 'Eventos ahora',
      events_processed: 'Eventos procesados',
      contacts_scope: 'Contactos en embudos',
      selected_deals: 'Deals en alcance',
      selected_contacts: 'Contactos en alcance',
      deal_contacts: 'Vínculos deal-contacto',
      deal_companies: 'Vínculos deal-compañía',
      stage_transitions: 'Transiciones de etapa',
      stage_transitions_processed: 'Transiciones procesadas',
      deal_sources: 'Fuentes de deals',
      custom_fields: 'Campos amoCRM',
      custom_fields_imported: 'Campos ahora',
      custom_fields_processed: 'Campos procesados',
      custom_field_values: 'Valores de campos',
      sources: 'Fuentes',
      tasks_enriched: 'Tareas enriquecidas',
    },
  };
  const labels = labelsByLocale[locale] ?? labelsByLocale.ru;
  return labels[key] ?? key;
}

function formatJobStage(stage: string | undefined, locale: string): string {
  const labelsByLocale: Record<string, Record<string, string>> = {
    ru: {
      pipelines: 'воронки',
      stages: 'этапы',
      users: 'пользователи',
      companies: 'компании',
      contacts: 'контакты',
      deals: 'сделки',
      tasks: 'задачи',
      tasks_enriched: 'расширенные задачи',
      contacts_scope: 'контакты среза',
      custom_fields: 'поля amoCRM',
      sources: 'источники',
      products: 'товары/услуги',
      deal_products: 'товары в сделках',
      notes: 'события/notes',
      messages: 'сообщения',
      events: 'история событий',
      stage_transitions: 'переходы этапов',
      waiting: 'ожидание',
    },
    en: {
      pipelines: 'pipelines',
      stages: 'stages',
      users: 'users',
      companies: 'companies',
      contacts: 'contacts',
      deals: 'deals',
      tasks: 'tasks',
      tasks_enriched: 'enriched tasks',
      contacts_scope: 'scope contacts',
      custom_fields: 'amoCRM fields',
      sources: 'sources',
      products: 'products/services',
      deal_products: 'deal products',
      notes: 'events/notes',
      messages: 'messages',
      events: 'event history',
      stage_transitions: 'stage transitions',
      waiting: 'waiting',
    },
    es: {
      pipelines: 'embudos',
      stages: 'etapas',
      users: 'usuarios',
      companies: 'compañías',
      contacts: 'contactos',
      deals: 'deals',
      tasks: 'tareas',
      tasks_enriched: 'tareas enriquecidas',
      contacts_scope: 'contactos del alcance',
      custom_fields: 'campos amoCRM',
      sources: 'fuentes',
      products: 'productos/servicios',
      deal_products: 'productos en deals',
      notes: 'eventos/notas',
      messages: 'mensajes',
      events: 'historial de eventos',
      stage_transitions: 'transiciones de etapa',
      waiting: 'en espera',
    },
  };
  const labels = labelsByLocale[locale] ?? labelsByLocale.ru;
  return stage ? labels[stage] ?? stage : labels.waiting;
}

function formatMessagesCoverage(
  coverage:
    | {
        messages_imported?: number;
        chats_seen?: number;
        chats_matched?: number;
        unmatched_chats?: number;
        skipped_reason?: string | null;
      }
    | undefined,
  locale: string,
): string {
  const imported = Number(coverage?.messages_imported ?? 0).toLocaleString(locale);
  const seen = Number(coverage?.chats_seen ?? 0).toLocaleString(locale);
  const matched = Number(coverage?.chats_matched ?? 0).toLocaleString(locale);
  const unmatched = Number(coverage?.unmatched_chats ?? 0).toLocaleString(locale);
  const skipped = coverage?.skipped_reason;
  if (locale === 'en') {
    return `Messages coverage: imported ${imported}, chats seen ${seen}, matched ${matched}, unmatched ${unmatched}${skipped ? `, skipped: ${skipped}` : ''}.`;
  }
  if (locale === 'es') {
    return `Cobertura de mensajes: importados ${imported}, chats encontrados ${seen}, vinculados ${matched}, sin vínculo ${unmatched}${skipped ? `, omitido: ${skipped}` : ''}.`;
  }
  return `Покрытие сообщений: импортировано ${imported}, чатов найдено ${seen}, связано ${matched}, без связи ${unmatched}${skipped ? `, пропущено: ${skipped}` : ''}.`;
}

const connectionDetailTextMap = {
  ru: {
    missingTokensToast: 'Не хватает {tokens} AIC9-токенов',
    autoUpdateTitle: 'Автообновление данных',
    mode: 'Режим',
    incrementalMode: 'Догрузка изменений',
    plan: 'Тариф',
    cadence: 'Частота',
    nextUpdate: 'Следующее обновление',
    stage: 'Этап',
    queuePosition: 'Позиция в очереди',
    timeLeft: 'Примерно осталось',
    estimatedRecords: 'Оценка записей',
    clientsInQuote: 'Клиентов в расчёте',
    recordsInQuote: 'Записей',
    estimatedTime: 'Время',
    tokensNeeded: 'Нужно токенов',
    tokensAvailable: 'Доступно токенов',
    tokensMissing: 'Не хватает',
    tokensEnough: 'Токенов хватает, можно запускать выгрузку.',
    tokensNotEnough: 'Недостаточно токенов для выгрузки за выбранный период.',
    topUpBalance: 'Пополнить баланс',
  },
  en: {
    missingTokensToast: 'Missing {tokens} AIC9 tokens',
    autoUpdateTitle: 'Data auto-update',
    mode: 'Mode',
    incrementalMode: 'Incremental update',
    plan: 'Plan',
    cadence: 'Frequency',
    nextUpdate: 'Next update',
    stage: 'Stage',
    queuePosition: 'Queue position',
    timeLeft: 'Approx. left',
    estimatedRecords: 'Estimated records',
    clientsInQuote: 'Clients in estimate',
    recordsInQuote: 'Records',
    estimatedTime: 'Time',
    tokensNeeded: 'Tokens needed',
    tokensAvailable: 'Tokens available',
    tokensMissing: 'Missing',
    tokensEnough: 'Enough tokens, export can be started.',
    tokensNotEnough: 'Not enough tokens for export in the selected period.',
    topUpBalance: 'Top up balance',
  },
  es: {
    missingTokensToast: 'Faltan {tokens} tokens AIC9',
    autoUpdateTitle: 'Actualización automática de datos',
    mode: 'Modo',
    incrementalMode: 'Carga incremental de cambios',
    plan: 'Plan',
    cadence: 'Frecuencia',
    nextUpdate: 'Próxima actualización',
    stage: 'Etapa',
    queuePosition: 'Posición en cola',
    timeLeft: 'Tiempo aprox.',
    estimatedRecords: 'Registros estimados',
    clientsInQuote: 'Clientes en el cálculo',
    recordsInQuote: 'Registros',
    estimatedTime: 'Tiempo',
    tokensNeeded: 'Tokens necesarios',
    tokensAvailable: 'Tokens disponibles',
    tokensMissing: 'Faltan',
    tokensEnough: 'Hay tokens suficientes, se puede iniciar la exportación.',
    tokensNotEnough: 'No hay tokens suficientes para exportar el periodo seleccionado.',
    topUpBalance: 'Recargar balance',
  },
} as const;

type ConnectionDetailTextKey = keyof typeof connectionDetailTextMap.ru;

function connectionDetailText(
  locale: string,
  key: ConnectionDetailTextKey,
  replacements?: Record<string, string>,
): string {
  const lang = locale === 'en' || locale === 'es' ? locale : 'ru';
  let value: string = connectionDetailTextMap[lang][key];
  if (replacements) {
    Object.entries(replacements).forEach(([name, replacement]) => {
      value = value.replace(`{${name}}`, replacement);
    });
  }
  return value;
}

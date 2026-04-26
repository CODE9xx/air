'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, CircleDollarSign, Clock3, GitBranch, Percent, TrendingUp, Users } from 'lucide-react';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';
import { toIntlLocale } from '@/lib/utils';

type SalesDashboard = {
  mock: boolean;
  filters: {
    period?: string | null;
    date_from: string | null;
    date_to: string | null;
    pipeline_id?: string | null;
    pipeline_ids: string[];
    active_pipeline_ids?: string[];
  };
  kpis: {
    total_deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    won_rate: number;
    lost_rate: number;
    revenue_rub: number;
    avg_deal_rub: number;
    date_from: string | null;
    date_to: string | null;
    pipeline_count: number;
    manager_count: number;
  };
  monthly_revenue: Array<{
    month: string | null;
    deals: number;
    won_deals: number;
    revenue_rub: number;
  }>;
  pipeline_breakdown: Array<{
    pipeline: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    revenue_rub: number;
  }>;
  status_breakdown: Array<{ status: string; deals: number; revenue_rub: number }>;
  stage_funnel: Array<{
    pipeline: string;
    stage: string;
    deals: number;
    revenue_rub: number;
  }>;
  manager_leaderboard: Array<{
    user_id: string;
    name: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    revenue_rub: number;
    avg_deal_rub: number;
  }>;
  top_deals: Array<{
    id: string;
    name: string;
    status: string;
    price_rub: number;
    pipeline: string | null;
    stage: string | null;
    manager: string | null;
    created_at: string | null;
    closed_at: string | null;
  }>;
  sales_cycle: {
    avg_won_cycle_days: number;
    avg_lost_cycle_days: number;
    avg_open_age_days: number;
    stale_open_deals: number;
    stale_open_amount_rub: number;
  };
  open_age_buckets: Array<{
    bucket: string;
    label: string;
    deals: number;
    amount_rub: number;
  }>;
  pipeline_health: Array<{
    pipeline: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    stale_open_deals: number;
    open_amount_rub: number;
    avg_open_age_days: number;
    oldest_open_age_days: number;
    won_rate: number;
  }>;
  manager_risk: Array<{
    user_id: string;
    name: string;
    open_deals: number;
    stale_open_deals: number;
    open_amount_rub: number;
    avg_open_age_days: number;
    oldest_open_age_days: number;
  }>;
};

type DashboardOptions = {
  mock: boolean;
  default_filters: {
    period?: string;
    date_from?: string | null;
    date_to?: string | null;
    pipeline_ids?: string[];
  };
  pipelines: Array<{ id: string; name: string; deals?: number }>;
};

type DashboardPeriod = 'active_export' | 'last_30' | 'last_90' | 'last_12_months' | 'all_time' | 'custom';

const STATUS_COLORS: Record<string, string> = {
  open: '#2563eb',
  won: '#059669',
  lost: '#dc2626',
  unknown: '#64748b',
};

const PIPELINE_COLORS = ['#2563eb', '#059669', '#d97706', '#7c3aed', '#0891b2', '#be123c'];

function buildDashboardQuery(
  period: DashboardPeriod,
  pipelineId: string | null,
  customDateFrom: string,
  customDateTo: string,
): Record<string, string> {
  const query: Record<string, string> = {};
  if (pipelineId) query.pipeline_id = pipelineId;
  if (period === 'all_time') {
    query.period = 'all_time';
    return query;
  }
  if (period === 'active_export') {
    query.period = 'active_export';
    return query;
  }
  query.period = 'custom';
  if (period === 'custom') {
    if (customDateFrom) query.date_from = customDateFrom;
    if (customDateTo) query.date_to = customDateTo;
    return query;
  }
  const days = period === 'last_30' ? 30 : period === 'last_90' ? 90 : 365;
  query.date_from = formatDateInput(addDays(new Date(), -days));
  query.date_to = formatDateInput(new Date());
  return query;
}

export default function ConnectionDashboardPage() {
  const t = useTranslations('cabinet.dashboard_page');
  const params = useParams<{ id: string; locale: string }>();
  const id = params?.id;
  const locale = toIntlLocale(params?.locale ?? 'ru');
  const [data, setData] = useState<SalesDashboard | null>(null);
  const [options, setOptions] = useState<DashboardOptions | null>(null);
  const [period, setPeriod] = useState<DashboardPeriod>('active_export');
  const [customDateFrom, setCustomDateFrom] = useState('');
  const [customDateTo, setCustomDateTo] = useState('');
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      setOptionsLoading(false);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setOptionsLoading(true);
    api
      .get<DashboardOptions>(`/crm/connections/${id}/dashboard/options`)
      .then((response) => {
        if (cancelled) return;
        setOptions(response);
        setSelectedPipelineId((current) => current ?? response.pipelines[0]?.id ?? null);
        if (response.default_filters.date_from) setCustomDateFrom(response.default_filters.date_from.slice(0, 10));
        if (response.default_filters.date_to) setCustomDateTo(response.default_filters.date_to.slice(0, 10));
      })
      .catch(() => {
        if (!cancelled) setOptions(null);
      })
      .finally(() => {
        if (!cancelled) setOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!id || optionsLoading) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    const query = buildDashboardQuery(period, selectedPipelineId, customDateFrom, customDateTo);
    api
      .get<SalesDashboard>(`/crm/connections/${id}/dashboard/sales`, { query })
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [customDateFrom, customDateTo, id, optionsLoading, period, selectedPipelineId]);

  const monthlyRevenue = useMemo(
    () =>
      (data?.monthly_revenue ?? []).map((item) => ({
        ...item,
        label: formatMonth(item.month, locale),
      })),
    [data?.monthly_revenue, locale],
  );
  const pipelineBreakdown = useMemo(
    () =>
      (data?.pipeline_breakdown ?? []).slice(0, 8).map((item) => ({
        ...item,
        label: shortLabel(item.pipeline, 26),
      })),
    [data?.pipeline_breakdown],
  );
  const stageFunnel = useMemo(
    () =>
      (data?.stage_funnel ?? [])
        .filter((item) => item.deals > 0)
        .sort((a, b) => b.deals - a.deals)
        .slice(0, 14)
        .map((item) => ({
          ...item,
          label: shortLabel(item.stage, 28),
        })),
    [data?.stage_funnel],
  );
  const managerLeaderboard = useMemo(
    () =>
      (data?.manager_leaderboard ?? []).slice(0, 12).map((item) => ({
        ...item,
        label: shortLabel(item.name, 24),
      })),
    [data?.manager_leaderboard],
  );
  const openAgeBuckets = useMemo(
    () => (data?.open_age_buckets ?? []).map((item) => ({ ...item, label: item.label })),
    [data?.open_age_buckets],
  );
  const pipelineHealth = useMemo(
    () =>
      (data?.pipeline_health ?? []).slice(0, 8).map((item) => ({
        ...item,
        label: shortLabel(item.pipeline, 28),
      })),
    [data?.pipeline_health],
  );
  const managerRisk = useMemo(
    () => (data?.manager_risk ?? []).slice(0, 8),
    [data?.manager_risk],
  );

  if (loading || optionsLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-28" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((item) => (
            <Skeleton key={item} className="h-32" />
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!data) {
    return <EmptyState title={t('noData')} />;
  }

  const periodLabel =
    data.filters.date_from || data.filters.date_to
      ? `${formatDate(data.filters.date_from, locale) ?? t('periodStart')} - ${
          formatDate(data.filters.date_to, locale) ?? t('periodNow')
        }`
      : `${t('allPeriod')} · ${formatDate(data.kpis.date_from, locale) ?? '-'} - ${
          formatDate(data.kpis.date_to, locale) ?? '-'
        }`;
  const selectedPipelines = data.filters.pipeline_ids.length
    ? selectedPipelineId
      ? options?.pipelines.find((item) => item.id === selectedPipelineId)?.name ?? t('selectedPipeline')
      : t('selectedPipelines', { count: data.filters.pipeline_ids.length })
    : t('allPipelines');

  return (
    <div className="space-y-5 pb-8">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-sm font-medium text-blue-700">{t('salesSubtitle')}</div>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal text-slate-950">
              {t('salesTitle')}
            </h1>
            <div className="mt-3 flex flex-wrap gap-2 text-sm text-slate-600">
              <span className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
                {periodLabel}
              </span>
              <span className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
                {selectedPipelines}
              </span>
              {data.mock && (
                <span className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-800">
                  {t('mockData')}
                </span>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:min-w-[520px]">
            <MiniStat label={t('pipelines')} value={formatNumber(data.kpis.pipeline_count, locale)} />
            <MiniStat label={t('managersCount')} value={formatNumber(data.kpis.manager_count, locale)} />
            <MiniStat label={t('openDeals')} value={formatNumber(data.kpis.open_deals, locale)} />
            <MiniStat label={t('lostDeals')} value={formatNumber(data.kpis.lost_deals, locale)} />
          </div>
        </div>
        <div className="mt-5 grid gap-3 border-t border-slate-100 pt-4 lg:grid-cols-[1.35fr_0.65fr]">
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              {t('analyticsPeriod')}
            </div>
            <div className="flex flex-wrap gap-2">
              {(['active_export', 'last_30', 'last_90', 'last_12_months', 'all_time', 'custom'] as DashboardPeriod[]).map(
                (item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setPeriod(item)}
                    className={
                      period === item
                        ? 'rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white'
                        : 'rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50'
                    }
                  >
                    {t(`period.${item}`)}
                  </button>
                ),
              )}
            </div>
            {period === 'custom' && (
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  type="date"
                  value={customDateFrom}
                  onChange={(event) => setCustomDateFrom(event.target.value)}
                  className="rounded-md border border-slate-200 px-3 py-2 text-sm"
                />
                <input
                  type="date"
                  value={customDateTo}
                  onChange={(event) => setCustomDateTo(event.target.value)}
                  className="rounded-md border border-slate-200 px-3 py-2 text-sm"
                />
              </div>
            )}
          </div>
          <div>
            <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-500">
              {t('analyticsPipeline')}
            </label>
            <select
              value={selectedPipelineId ?? ''}
              onChange={(event) => setSelectedPipelineId(event.target.value || null)}
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800"
            >
              {(options?.pipelines ?? []).map((pipeline) => (
                <option key={pipeline.id} value={pipeline.id}>
                  {pipeline.name}
                  {typeof pipeline.deals === 'number' ? ` · ${formatNumber(pipeline.deals, locale)}` : ''}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-slate-500">{t('analyticsPipelineHint')}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          icon={<TrendingUp className="h-5 w-5" />}
          label={t('totalDeals')}
          value={formatNumber(data.kpis.total_deals, locale)}
          tone="blue"
        />
        <KpiCard
          icon={<CircleDollarSign className="h-5 w-5" />}
          label={t('revenue')}
          value={formatRub(data.kpis.revenue_rub, locale)}
          tone="emerald"
        />
        <KpiCard
          icon={<CircleDollarSign className="h-5 w-5" />}
          label={t('avgDeal')}
          value={formatRub(data.kpis.avg_deal_rub, locale)}
          tone="amber"
        />
        <KpiCard
          icon={<Percent className="h-5 w-5" />}
          label={t('wonRate')}
          value={formatPercent(data.kpis.won_rate, locale)}
          tone="violet"
        />
        <KpiCard
          icon={<GitBranch className="h-5 w-5" />}
          label={t('wonDeals')}
          value={formatNumber(data.kpis.won_deals, locale)}
          tone="cyan"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)]">
        <Panel title={t('riskTitle')} subtitle={t('riskHint')}>
          <div className="grid gap-3 sm:grid-cols-2">
            <RiskStat
              icon={<AlertTriangle className="h-4 w-4" />}
              label={t('staleDeals')}
              value={formatNumber(data.sales_cycle.stale_open_deals, locale)}
              hint={t('staleDealsHint')}
              tone="rose"
            />
            <RiskStat
              icon={<CircleDollarSign className="h-4 w-4" />}
              label={t('staleAmount')}
              value={formatRub(data.sales_cycle.stale_open_amount_rub, locale)}
              hint={t('staleAmountHint')}
              tone="amber"
            />
            <RiskStat
              icon={<Clock3 className="h-4 w-4" />}
              label={t('avgOpenAge')}
              value={formatDays(data.sales_cycle.avg_open_age_days, locale)}
              hint={t('avgOpenAgeHint')}
              tone="blue"
            />
            <RiskStat
              icon={<TrendingUp className="h-4 w-4" />}
              label={t('avgWonCycle')}
              value={formatDays(data.sales_cycle.avg_won_cycle_days, locale)}
              hint={t('avgWonCycleHint')}
              tone="emerald"
            />
          </div>
        </Panel>

        <Panel title={t('openAgeTitle')} subtitle={t('openAgeHint')}>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={openAgeBuckets} margin={{ top: 8, right: 18, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis yAxisId="left" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => shortMoney(Number(value), locale)}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === 'amount_rub'
                      ? [formatRub(Number(value), locale), t('openAmount')]
                      : [formatNumber(Number(value), locale), t('deals')]
                  }
                />
                <Legend />
                <Bar yAxisId="left" dataKey="deals" name={t('deals')} fill="#2563eb" radius={[4, 4, 0, 0]} />
                <Line
                  yAxisId="right"
                  dataKey="amount_rub"
                  name={t('openAmount')}
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <Panel title={t('revenueDynamics')} subtitle={t('revenueDynamicsHint')}>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={monthlyRevenue} margin={{ top: 10, right: 18, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => shortMoney(Number(value), locale)}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === 'revenue_rub'
                      ? [formatRub(Number(value), locale), t('revenue')]
                      : [formatNumber(Number(value), locale), String(name)]
                  }
                />
                <Legend />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="revenue_rub"
                  name={t('revenue')}
                  stroke="#059669"
                  fill="#d1fae5"
                  strokeWidth={2}
                />
                <Bar
                  yAxisId="right"
                  dataKey="deals"
                  name={t('deals')}
                  fill="#2563eb"
                  radius={[4, 4, 0, 0]}
                  barSize={22}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="won_deals"
                  name={t('wonDeals')}
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title={t('statusStructure')} subtitle={t('statusStructureHint')}>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data.status_breakdown}
                  dataKey="deals"
                  nameKey="status"
                  innerRadius={72}
                  outerRadius={118}
                  paddingAngle={2}
                >
                  {data.status_breakdown.map((item) => (
                    <Cell key={item.status} fill={STATUS_COLORS[item.status] ?? STATUS_COLORS.unknown} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => [formatNumber(Number(value), locale), t('deals')]}
                  labelFormatter={(label) => statusLabel(String(label), t)}
                />
                <Legend formatter={(value) => statusLabel(String(value), t)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Panel title={t('pipelinesRevenue')} subtitle={t('pipelinesRevenueHint')}>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={pipelineBreakdown} margin={{ top: 10, right: 18, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis yAxisId="left" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => shortMoney(Number(value), locale)}
                />
                <Tooltip
                  formatter={(value, name) =>
                    name === 'revenue_rub'
                      ? [formatRub(Number(value), locale), t('revenue')]
                      : [formatNumber(Number(value), locale), String(name)]
                  }
                />
                <Legend />
                <Bar yAxisId="left" dataKey="deals" name={t('deals')} fill="#2563eb" radius={[4, 4, 0, 0]} />
                <Bar
                  yAxisId="left"
                  dataKey="won_deals"
                  name={t('wonDeals')}
                  fill="#059669"
                  radius={[4, 4, 0, 0]}
                />
                <Line
                  yAxisId="right"
                  dataKey="revenue_rub"
                  name={t('revenue')}
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title={t('stageLoad')} subtitle={t('stageLoadHint')}>
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={stageFunnel}
                layout="vertical"
                margin={{ top: 8, right: 18, left: 24, bottom: 8 }}
              >
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={150}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  formatter={(value) => [formatNumber(Number(value), locale), t('deals')]}
                  labelFormatter={(label) => String(label)}
                />
                <Bar dataKey="deals" name={t('deals')} radius={[0, 4, 4, 0]}>
                  {stageFunnel.map((_, index) => (
                    <Cell key={index} fill={PIPELINE_COLORS[index % PIPELINE_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <Panel title={t('pipelineHealthTitle')} subtitle={t('pipelineHealthHint')}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-3 pr-4 font-medium">{t('pipeline')}</th>
                  <th className="py-3 pr-4 text-right font-medium">{t('openDeals')}</th>
                  <th className="py-3 pr-4 text-right font-medium">{t('staleDeals')}</th>
                  <th className="py-3 pr-4 text-right font-medium">{t('avgAge')}</th>
                  <th className="py-3 text-right font-medium">{t('openAmount')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pipelineHealth.map((pipeline) => (
                  <tr key={pipeline.pipeline}>
                    <td className="py-3 pr-4">
                      <div className="font-medium text-slate-950">{pipeline.pipeline}</div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100">
                        <div
                          className="h-2 rounded-full bg-blue-600"
                          style={{
                            width: `${Math.min(
                              100,
                              Math.round((pipeline.open_deals / Math.max(1, data.kpis.open_deals)) * 100),
                            )}%`,
                          }}
                        />
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-right text-slate-700">
                      {formatNumber(pipeline.open_deals, locale)}
                    </td>
                    <td className="py-3 pr-4 text-right font-semibold text-rose-700">
                      {formatNumber(pipeline.stale_open_deals, locale)}
                    </td>
                    <td className="py-3 pr-4 text-right text-slate-700">
                      {formatDays(pipeline.avg_open_age_days, locale)}
                    </td>
                    <td className="py-3 text-right font-semibold text-slate-950">
                      {formatRub(pipeline.open_amount_rub, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title={t('managerRiskTitle')} subtitle={t('managerRiskHint')}>
          <div className="space-y-3">
            {managerRisk.map((manager, index) => (
              <div key={manager.user_id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-950">
                      {index + 1}. {manager.name}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {formatNumber(manager.open_deals, locale)} {t('openDeals').toLowerCase()} ·{' '}
                      {formatDays(manager.avg_open_age_days, locale)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-rose-700">
                      {formatNumber(manager.stale_open_deals, locale)}
                    </div>
                    <div className="text-xs text-slate-500">{t('staleDeals').toLowerCase()}</div>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                  <span>{t('openAmount')}</span>
                  <span className="font-semibold text-slate-800">
                    {formatRub(manager.open_amount_rub, locale)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <Panel title={t('managerLeaderboard')} subtitle={t('managerLeaderboardHint')}>
          <div className="space-y-3">
            {managerLeaderboard.map((manager, index) => (
              <div key={manager.user_id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-950">
                      {index + 1}. {manager.name}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {formatNumber(manager.deals, locale)} {t('deals').toLowerCase()} ·{' '}
                      {formatNumber(manager.won_deals, locale)} {t('wonDeals').toLowerCase()}
                    </div>
                  </div>
                  <div className="text-right text-sm font-semibold text-emerald-700">
                    {formatRub(manager.revenue_rub, locale)}
                  </div>
                </div>
                <div className="mt-3 h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-emerald-600"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.round((manager.revenue_rub / Math.max(1, data.kpis.revenue_rub)) * 100),
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title={t('topDeals')} subtitle={t('topDealsHint')}>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-3 pr-4 font-medium">{t('deal')}</th>
                  <th className="py-3 pr-4 font-medium">{t('pipeline')}</th>
                  <th className="py-3 pr-4 font-medium">{t('manager')}</th>
                  <th className="py-3 pr-4 font-medium">{t('status')}</th>
                  <th className="py-3 text-right font-medium">{t('amount')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.top_deals.slice(0, 12).map((deal) => (
                  <tr key={deal.id}>
                    <td className="max-w-[260px] py-3 pr-4">
                      <div className="truncate font-medium text-slate-950">{deal.name}</div>
                      <div className="text-xs text-slate-500">{formatDate(deal.created_at, locale) ?? '-'}</div>
                    </td>
                    <td className="py-3 pr-4 text-slate-700">{deal.pipeline ?? '-'}</td>
                    <td className="py-3 pr-4 text-slate-700">{deal.manager ?? '-'}</td>
                    <td className="py-3 pr-4">
                      <span className={statusBadgeClass(deal.status)}>{statusLabel(deal.status, t)}</span>
                    </td>
                    <td className="py-3 text-right font-semibold text-slate-950">
                      {formatRub(deal.price_rub, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </section>

      <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
        <div className="flex items-center gap-2 font-medium text-slate-800">
          <Users className="h-4 w-4" />
          {t('communicationsTitle')}
        </div>
        <p className="mt-1">{t('communicationsBody')}</p>
      </section>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-slate-950">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function KpiCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: 'blue' | 'emerald' | 'amber' | 'violet' | 'cyan';
}) {
  const toneClass = {
    blue: 'bg-blue-50 text-blue-700 border-blue-100',
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    amber: 'bg-amber-50 text-amber-700 border-amber-100',
    violet: 'bg-violet-50 text-violet-700 border-violet-100',
    cyan: 'bg-cyan-50 text-cyan-700 border-cyan-100',
  }[tone];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
      <div className={`inline-flex h-9 w-9 items-center justify-center rounded-md border ${toneClass}`}>
        {icon}
      </div>
      <div className="mt-4 text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function RiskStat({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint: string;
  tone: 'rose' | 'amber' | 'blue' | 'emerald';
}) {
  const toneClass = {
    rose: 'bg-rose-50 text-rose-700 border-rose-100',
    amber: 'bg-amber-50 text-amber-700 border-amber-100',
    blue: 'bg-blue-50 text-blue-700 border-blue-100',
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  }[tone];
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className={`inline-flex h-8 w-8 items-center justify-center rounded-md border ${toneClass}`}>
        {icon}
      </div>
      <div className="mt-3 text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-950">{value}</div>
      <div className="mt-1 text-xs leading-5 text-slate-500">{hint}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function formatNumber(value: number, locale: string) {
  return new Intl.NumberFormat(locale).format(value || 0);
}

function formatRub(value: number, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function shortMoney(value: number, locale: string) {
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value || 0);
}

function formatPercent(value: number, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(value || 0);
}

function formatDays(value: number, locale: string) {
  const rounded = Math.round(value || 0);
  const suffix = locale.startsWith('ru') ? 'дн.' : 'd';
  return `${new Intl.NumberFormat(locale).format(rounded)} ${suffix}`;
}

function formatDate(value: string | null, locale: string) {
  if (!value) return null;
  return new Intl.DateTimeFormat(locale, { day: '2-digit', month: 'short', year: 'numeric' }).format(
    new Date(value),
  );
}

function addDays(value: Date, days: number) {
  const copy = new Date(value);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function formatDateInput(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatMonth(value: string | null, locale: string) {
  if (!value) return '-';
  return new Intl.DateTimeFormat(locale, { month: 'short', year: '2-digit' }).format(new Date(value));
}

function shortLabel(value: string | null | undefined, max: number) {
  const safe = value || '-';
  return safe.length > max ? `${safe.slice(0, max - 1)}…` : safe;
}

function statusLabel(status: string, t: ReturnType<typeof useTranslations>) {
  if (status === 'open') return t('statusOpen');
  if (status === 'won') return t('statusWon');
  if (status === 'lost') return t('statusLost');
  return t('statusUnknown');
}

function statusBadgeClass(status: string) {
  if (status === 'won') return 'rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700';
  if (status === 'lost') return 'rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700';
  if (status === 'open') return 'rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700';
  return 'rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600';
}

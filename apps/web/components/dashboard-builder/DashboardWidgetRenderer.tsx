'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ReactNode } from 'react';
import { cn, toIntlLocale } from '@/lib/utils';
import type { DashboardWidget, SalesDashboardSnapshot } from './types';

type Props = {
  widget: DashboardWidget;
  sales: SalesDashboardSnapshot | null;
  locale: string;
  compact?: boolean;
};

const PHASE2B_WIDGET_TYPES: DashboardWidget['widget_type'][] = [
  'phase2b_calls',
  'phase2b_messages',
  'phase2b_email',
  'phase2b_sources',
  'phase2b_lost_reasons',
];

export function DashboardWidgetRenderer({ widget, sales, locale, compact = false }: Props) {
  const intlLocale = toIntlLocale(locale);
  const availability = typeof widget.config?.availability === 'string' ? widget.config.availability : 'available';
  if (PHASE2B_WIDGET_TYPES.includes(widget.widget_type)) {
    return (
      <WidgetShell title={widget.title} compact={compact} tone="amber">
        <Phase2BPlaceholder />
      </WidgetShell>
    );
  }
  if (availability === 'requires_mapping') {
    return (
      <WidgetShell title={widget.title} compact={compact} tone="amber">
        <SetupState title="Нужно настроить поле" body="Выберите custom field amoCRM, из которого CODE9 будет считать эту метрику." />
      </WidgetShell>
    );
  }
  if (availability === 'requires_integration') {
    return (
      <WidgetShell title={widget.title} compact={compact} tone="amber">
        <SetupState title="Нужно подключить интеграцию" body="Для этого блока требуется импорт задач, звонков, сообщений, почты или событий сделки." />
      </WidgetShell>
    );
  }
  if (availability === 'requires_ai') {
    return (
      <WidgetShell title={widget.title} compact={compact} tone="amber">
        <SetupState title="Нужно включить AI-анализ" body="Перед запуском CODE9 покажет оценку токенов и будет анализировать данные только внутри этого клиента." />
      </WidgetShell>
    );
  }

  if (!sales) {
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="flex h-full items-center justify-center text-sm text-slate-500">
          Нет данных
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type.startsWith('kpi_')) {
    const kpi = getKpi(widget.widget_type, sales, intlLocale);
    return (
      <WidgetShell title={widget.title} compact={compact} tone={kpi.tone}>
        <div className="flex h-full flex-col justify-end">
          <div className="text-3xl font-semibold tracking-normal text-slate-950">{kpi.value}</div>
          <div className="mt-2 text-sm text-slate-500">{kpi.hint}</div>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'line_dynamics') {
    const rows = sales.monthly_revenue.map((item) => ({
      ...item,
      label: formatMonth(item.month, intlLocale),
      lost_deals: item.lost_deals ?? 0,
    }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 10, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              formatter={(value, name) => [
                name === 'revenue_rub'
                  ? formatRub(Number(value), intlLocale)
                  : formatNumber(Number(value), intlLocale),
                metricLabel(String(name)),
              ]}
            />
            <Bar dataKey="deals" fill="#2563eb" name="deals" radius={[4, 4, 0, 0]} />
            <Line dataKey="won_deals" stroke="#059669" strokeWidth={2} dot={false} name="won_deals" />
            <Line dataKey="lost_deals" stroke="#dc2626" strokeWidth={2} dot={false} name="lost_deals" />
          </ComposedChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'revenue_dynamics') {
    const rows = sales.monthly_revenue.map((item) => ({
      ...item,
      label: formatMonth(item.month, intlLocale),
    }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 10, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              formatter={(value, name) => [
                name === 'revenue_rub'
                  ? formatRub(Number(value), intlLocale)
                  : formatNumber(Number(value), intlLocale),
                metricLabel(String(name)),
              ]}
            />
            <Bar yAxisId="left" dataKey="revenue_rub" fill="#2563eb" name="revenue_rub" radius={[4, 4, 0, 0]} />
            <Line yAxisId="right" dataKey="won_deals" stroke="#059669" strokeWidth={2} dot={false} name="won_deals" />
          </ComposedChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'status_structure') {
    const rows = (sales.status_breakdown ?? []).map((item) => ({
      ...item,
      label: statusLabel(item.status),
    }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 6, right: 10, left: -18, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value) => [formatNumber(Number(value), intlLocale), 'Сделки']} />
            <Bar dataKey="deals" fill="#2563eb" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'stage_funnel') {
    const rows = sales.stage_funnel
      .filter((item) => item.deals > 0)
      .slice(0, 14)
      .map((item) => ({ ...item, label: shortLabel(item.stage, 24) }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 6, right: 10, left: 28, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value) => [formatNumber(Number(value), intlLocale), 'Сделки']} />
            <Bar dataKey="deals" fill="#2563eb" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'manager_table') {
    const rows = buildManagerRows(sales).slice(0, 14);
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="h-full overflow-auto">
          <table className="min-w-[820px] w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Ответственный</th>
                <th className="py-2 pr-3 text-right font-medium">Заявки</th>
                <th className="py-2 pr-3 text-right font-medium">Колл</th>
                <th className="py-2 pr-3 text-right font-medium">Продаж</th>
                <th className="py-2 pr-3 text-right font-medium">Не продаж</th>
                <th className="py-2 pr-3 text-right font-medium">Сумма</th>
                <th className="py-2 pr-3 text-right font-medium">Конверсия</th>
                <th className="py-2 pr-3 text-right font-medium">Сообщ.</th>
                <th className="py-2 text-right font-medium">Почта</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((manager) => (
                <tr key={manager.user_id}>
                  <td className="py-2 pr-3 font-medium text-slate-950">{manager.name}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.applications, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.calls, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.sales_count, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.not_sales_count, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right font-semibold">{formatRub(manager.sales_amount, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatPercent(manager.conversion, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.messages_count, intlLocale)}</td>
                  <td className="py-2 text-right">{formatNumber(manager.emails_sent, intlLocale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'manager_revenue_rank' || widget.widget_type === 'manager_conversion_rank') {
    const rows = buildManagerRows(sales)
      .slice()
      .sort((a, b) =>
        widget.widget_type === 'manager_revenue_rank'
          ? b.sales_amount - a.sales_amount
          : b.conversion - a.conversion,
      )
      .slice(0, 10)
      .map((item) => ({
        name: shortLabel(item.name, 18),
        value: widget.widget_type === 'manager_revenue_rank' ? item.sales_amount : Math.round(item.conversion * 1000) / 10,
      }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 6, right: 10, left: 34, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              formatter={(value) => [
                widget.widget_type === 'manager_revenue_rank'
                  ? formatRub(Number(value), intlLocale)
                  : `${formatNumber(Number(value), intlLocale)}%`,
                widget.widget_type === 'manager_revenue_rank' ? 'Сумма' : 'Конверсия',
              ]}
            />
            <Bar dataKey="value" fill="#2563eb" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'manager_risk') {
    const rows = sales.manager_risk ?? [];
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="h-full overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Менеджер</th>
                <th className="py-2 pr-3 text-right font-medium">Открытые</th>
                <th className="py-2 pr-3 text-right font-medium">Зависшие</th>
                <th className="py-2 pr-3 text-right font-medium">Возраст</th>
                <th className="py-2 text-right font-medium">Сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((manager) => (
                <tr key={manager.user_id}>
                  <td className="py-2 pr-3 font-medium text-slate-950">{manager.name}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(manager.open_deals, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right text-rose-600">{formatNumber(manager.stale_open_deals, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatDays(manager.avg_open_age_days, intlLocale)}</td>
                  <td className="py-2 text-right font-semibold">{formatRub(manager.open_amount_rub, intlLocale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'top_deals') {
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="h-full overflow-auto">
          <table className="w-full text-left text-sm">
            <tbody className="divide-y divide-slate-100">
              {sales.top_deals.slice(0, 10).map((deal) => (
                <tr key={deal.id}>
                  <td className="py-2 pr-3">
                    <div className="font-medium text-slate-950">{deal.name}</div>
                    <div className="text-xs text-slate-500">{deal.pipeline ?? '-'}</div>
                  </td>
                  <td className="py-2 text-right font-semibold">{formatRub(deal.price_rub, intlLocale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'pipeline_table') {
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="h-full overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Воронка</th>
                <th className="py-2 pr-3 text-right font-medium">Заявки</th>
                <th className="py-2 pr-3 text-right font-medium">Продаж</th>
                <th className="py-2 text-right font-medium">Сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sales.pipeline_breakdown.slice(0, 12).map((pipeline) => (
                <tr key={pipeline.pipeline}>
                  <td className="py-2 pr-3 font-medium text-slate-950">{pipeline.pipeline}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(pipeline.deals, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(pipeline.won_deals, intlLocale)}</td>
                  <td className="py-2 text-right font-semibold">{formatRub(pipeline.revenue_rub, intlLocale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'pipeline_health') {
    const rows = sales.pipeline_health ?? [];
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <div className="h-full overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Воронка</th>
                <th className="py-2 pr-3 text-right font-medium">Открытые</th>
                <th className="py-2 pr-3 text-right font-medium">Зависшие</th>
                <th className="py-2 pr-3 text-right font-medium">Конверсия</th>
                <th className="py-2 text-right font-medium">Открытая сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((pipeline) => (
                <tr key={pipeline.pipeline}>
                  <td className="py-2 pr-3 font-medium text-slate-950">{pipeline.pipeline}</td>
                  <td className="py-2 pr-3 text-right">{formatNumber(pipeline.open_deals, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right text-rose-600">{formatNumber(pipeline.stale_open_deals, intlLocale)}</td>
                  <td className="py-2 pr-3 text-right">{formatPercent(pipeline.won_rate, intlLocale)}</td>
                  <td className="py-2 text-right font-semibold">{formatRub(pipeline.open_amount_rub, intlLocale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'pipeline_stale') {
    const rows = (sales.pipeline_health ?? []).map((item) => ({
      label: shortLabel(item.pipeline, 20),
      stale_open_deals: item.stale_open_deals,
    }));
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 6, right: 10, left: 28, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value) => [formatNumber(Number(value), intlLocale), 'Зависшие']} />
            <Bar dataKey="stale_open_deals" fill="#dc2626" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  if (widget.widget_type === 'open_age_buckets') {
    const rows = sales.open_age_buckets ?? [];
    return (
      <WidgetShell title={widget.title} compact={compact}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 6, right: 10, left: -18, bottom: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip formatter={(value) => [formatNumber(Number(value), intlLocale), 'Открытые сделки']} />
            <Bar dataKey="deals" fill="#f59e0b" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </WidgetShell>
    );
  }

  return (
    <WidgetShell title={widget.title} compact={compact}>
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Виджет пока не поддержан
      </div>
    </WidgetShell>
  );
}

function WidgetShell({
  title,
  children,
  compact,
  tone = 'default',
}: {
  title: string;
  children: ReactNode;
  compact: boolean;
  tone?: 'default' | 'blue' | 'green' | 'red' | 'amber';
}) {
  const toneClass = {
    default: 'border-slate-200 bg-white',
    blue: 'border-blue-100 bg-blue-50/40',
    green: 'border-emerald-100 bg-emerald-50/40',
    red: 'border-rose-100 bg-rose-50/40',
    amber: 'border-amber-100 bg-amber-50/40',
  }[tone];
  return (
    <section className={cn('flex h-full min-h-0 flex-col rounded-lg border p-4 shadow-soft', toneClass)}>
      <div className={cn('mb-3 shrink-0 font-semibold text-slate-950', compact ? 'text-sm' : 'text-base')}>
        {title}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

function getKpi(type: DashboardWidget['widget_type'], sales: SalesDashboardSnapshot, locale: string) {
  if (type === 'kpi_open') {
    return { value: formatNumber(sales.kpis.open_deals, locale), hint: 'Открытые сделки', tone: 'blue' as const };
  }
  if (type === 'kpi_sales_amount') {
    return { value: formatRub(sales.kpis.revenue_rub, locale), hint: 'Сумма успешных сделок', tone: 'green' as const };
  }
  if (type === 'kpi_sales_count') {
    return { value: formatNumber(sales.kpis.won_deals, locale), hint: 'Успешные сделки', tone: 'green' as const };
  }
  if (type === 'kpi_lost') {
    return { value: formatNumber(sales.kpis.lost_deals, locale), hint: 'Проигранные сделки', tone: 'red' as const };
  }
  if (type === 'kpi_conversion') {
    return { value: formatPercent(sales.kpis.won_rate, locale), hint: 'Продажи / заявки', tone: 'amber' as const };
  }
  if (type === 'kpi_avg_deal') {
    return { value: formatRub(sales.kpis.avg_deal_rub ?? 0, locale), hint: 'Средний успешный чек', tone: 'green' as const };
  }
  if (type === 'kpi_pipeline_count') {
    return { value: formatNumber(sales.kpis.pipeline_count ?? 0, locale), hint: 'Воронки в выгрузке', tone: 'blue' as const };
  }
  if (type === 'kpi_manager_count') {
    return { value: formatNumber(sales.kpis.manager_count ?? 0, locale), hint: 'Активные менеджеры', tone: 'blue' as const };
  }
  return { value: formatNumber(sales.kpis.total_deals, locale), hint: 'Все заявки за период', tone: 'blue' as const };
}

function Phase2BPlaceholder() {
  return (
    <div className="flex h-full flex-col justify-center rounded-md border border-dashed border-amber-200 bg-white/70 p-4 text-sm text-slate-600">
      <div className="font-semibold text-slate-950">Данные ещё не импортированы</div>
      <div className="mt-2 leading-5">
        Блок появится после отдельной выгрузки коммуникаций Phase 2B. Сейчас фиктивные значения не показываем.
      </div>
    </div>
  );
}

function SetupState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full flex-col justify-center rounded-md border border-dashed border-amber-200 bg-white/70 p-4 text-sm text-slate-600">
      <div className="font-semibold text-slate-950">{title}</div>
      <div className="mt-2 leading-5">{body}</div>
    </div>
  );
}

function buildManagerRows(sales: SalesDashboardSnapshot) {
  if (sales.manager_metrics?.length) return sales.manager_metrics;
  return (sales.manager_leaderboard ?? []).map((manager) => ({
    user_id: manager.user_id,
    name: manager.name,
    applications: manager.deals,
    calls: 0,
    sales_count: manager.won_deals,
    not_sales_count: manager.lost_deals,
    sales_amount: manager.revenue_rub,
    conversion: manager.won_deals / Math.max(1, manager.deals),
    calls_in: 0,
    calls_out: 0,
    calls_duration_sec: 0,
    messages_count: 0,
    emails_sent: 0,
    currency: 'RUB',
  }));
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

function formatPercent(value: number, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(value || 0);
}

function formatDays(value: number, locale: string) {
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value || 0)} дн.`;
}

function formatMonth(value: string | null, locale: string) {
  if (!value) return '-';
  return new Intl.DateTimeFormat(locale, { month: 'short', year: '2-digit' }).format(new Date(value));
}

function shortLabel(value: string | null | undefined, max: number) {
  const safe = value || '-';
  return safe.length > max ? `${safe.slice(0, max - 1)}...` : safe;
}

function metricLabel(value: string) {
  if (value === 'deals') return 'Заявки';
  if (value === 'won_deals') return 'Продажи';
  if (value === 'lost_deals') return 'Проиграно';
  if (value === 'revenue_rub') return 'Сумма';
  return value;
}

function statusLabel(value: string) {
  if (value === 'open') return 'Открытые';
  if (value === 'won') return 'Продажи';
  if (value === 'lost') return 'Не реализовано';
  return value || '-';
}

'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { Responsive, WidthProvider, type Layout } from 'react-grid-layout';
import { ChevronLeft, ChevronRight, Copy, Eye, Plus, RotateCcw, Save, Search, Trash2 } from 'lucide-react';
import { DashboardWidgetRenderer } from '@/components/dashboard-builder/DashboardWidgetRenderer';
import type {
  DashboardBuilderPayload,
  DashboardPage,
  DashboardTemplate,
  DashboardWidget,
  DashboardWidgetType,
  SalesDashboardSnapshot,
} from '@/components/dashboard-builder/types';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

const ResponsiveGridLayout = WidthProvider(Responsive);

type CatalogItem = DashboardBuilderPayload['widget_catalog'][number];

const defaultPages: DashboardPage[] = [
  { page_key: 'sales', title: 'Продажи' },
  { page_key: 'pipelines', title: 'Воронки' },
  { page_key: 'managers', title: 'Менеджеры' },
  { page_key: 'risks', title: 'Риски' },
];

const fallbackCatalog: CatalogItem[] = [
  { widget_type: 'kpi_applications', title: 'Заявки', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_open', title: 'Открытые', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_sales_amount', title: 'Продажи руб', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_sales_count', title: 'Продаж', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_lost', title: 'Не реализовано', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_avg_deal', title: 'Средний чек', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'kpi_conversion', title: 'Конверсия', group: 'kpi', w: 3, h: 3 },
  { widget_type: 'line_dynamics', title: 'Заявки / продажи / проиграно', group: 'dynamics', w: 8, h: 5 },
  { widget_type: 'revenue_dynamics', title: 'Выручка и продажи', group: 'dynamics', w: 8, h: 5 },
  { widget_type: 'status_structure', title: 'Структура статусов', group: 'dynamics', w: 5, h: 5 },
  { widget_type: 'stage_funnel', title: 'Воронка по этапам', group: 'pipelines', w: 6, h: 5 },
  { widget_type: 'pipeline_table', title: 'Таблица воронок', group: 'pipelines', w: 6, h: 5 },
  { widget_type: 'pipeline_health', title: 'Здоровье воронок', group: 'pipelines', w: 7, h: 5 },
  { widget_type: 'pipeline_stale', title: 'Зависшие по воронкам', group: 'pipelines', w: 6, h: 5 },
  { widget_type: 'manager_table', title: 'Таблица менеджеров', group: 'managers', w: 8, h: 6 },
  { widget_type: 'manager_revenue_rank', title: 'Менеджеры по выручке', group: 'managers', w: 6, h: 5 },
  { widget_type: 'manager_conversion_rank', title: 'Менеджеры по конверсии', group: 'managers', w: 6, h: 5 },
  { widget_type: 'manager_risk', title: 'Риски по менеджерам', group: 'managers', w: 7, h: 5 },
  { widget_type: 'top_deals', title: 'Топ сделок', group: 'risks', w: 6, h: 5 },
  { widget_type: 'open_age_buckets', title: 'Возраст открытых сделок', group: 'risks', w: 7, h: 5 },
  { widget_type: 'phase2b_calls', title: 'Звонки', group: 'phase2b', w: 4, h: 3, placeholder: true },
  { widget_type: 'phase2b_messages', title: 'Сообщения', group: 'phase2b', w: 4, h: 3, placeholder: true },
  { widget_type: 'phase2b_email', title: 'Почта', group: 'phase2b', w: 4, h: 3, placeholder: true },
  { widget_type: 'phase2b_sources', title: 'Источники', group: 'phase2b', w: 4, h: 3, placeholder: true },
  { widget_type: 'phase2b_lost_reasons', title: 'Причины отказов', group: 'phase2b', w: 5, h: 4, placeholder: true },
];

const groupLabels: Record<string, string> = {
  kpi: 'KPI',
  dynamics: 'Динамика',
  pipelines: 'Воронки',
  managers: 'Менеджеры',
  risks: 'Риски',
  phase2b: 'Phase 2B',
  sales: 'Продажи',
  finance: 'Финансы',
  counterparties: 'Клиенты',
  marketing: 'Маркетинг',
  tasks: 'Задачи',
  calls: 'Звонки',
  communications: 'Сообщения и почта',
  ai: 'AI',
};

const quickTemplates: Array<{ title: string; widgets: DashboardWidgetType[] }> = [
  { title: 'Продажи', widgets: ['kpi_applications', 'kpi_sales_count', 'kpi_sales_amount', 'kpi_conversion', 'line_dynamics'] },
  { title: 'РОП', widgets: ['manager_table', 'manager_revenue_rank', 'manager_conversion_rank', 'manager_risk'] },
  { title: 'Воронки', widgets: ['stage_funnel', 'pipeline_table', 'pipeline_health', 'pipeline_stale'] },
  { title: 'Риски', widgets: ['open_age_buckets', 'manager_risk', 'top_deals', 'status_structure'] },
];

const fallbackTemplates: DashboardTemplate[] = [
  { template_key: 'sales_leads', title: 'Продажи и лиды', category: 'sales', widgets: ['kpi_applications', 'kpi_sales_count', 'kpi_sales_amount', 'kpi_conversion', 'line_dynamics'] },
  { template_key: 'revenue_avg_check', title: 'Выручка и средний чек', category: 'finance', widgets: ['kpi_sales_amount', 'kpi_avg_deal', 'revenue_dynamics'] },
  { template_key: 'counterparties', title: 'Клиенты и контрагенты', category: 'counterparties', widgets: ['counterparty_count', 'counterparty_top_paid', 'counterparty_top_debt', 'counterparty_table'] },
  { template_key: 'calls', title: 'Звонки', category: 'calls', widgets: ['calls_count', 'calls_in_out_dynamics', 'calls_duration_by_manager'] },
  { template_key: 'ai_quality', title: 'AI-контроль качества', category: 'ai', widgets: ['ai_script_adherence', 'ai_objection_reasons', 'ai_manager_score'] },
];

export default function DashboardBuilderPage() {
  const params = useParams<{ id: string; locale: string }>();
  const connectionId = params?.id;
  const locale = params?.locale ?? 'ru';
  const [builder, setBuilder] = useState<DashboardBuilderPayload | null>(null);
  const [pages, setPages] = useState<DashboardPage[]>(defaultPages);
  const [activePageKey, setActivePageKey] = useState(defaultPages[0].page_key);
  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [sales, setSales] = useState<SalesDashboardSnapshot | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [catalogSearch, setCatalogSearch] = useState('');
  const [availabilityFilter, setAvailabilityFilter] = useState<
    'all' | 'available' | 'requires_mapping' | 'requires_integration' | 'requires_ai'
  >('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!connectionId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get<DashboardBuilderPayload>(`/crm/connections/${connectionId}/dashboard-builder`),
      api.get<SalesDashboardSnapshot>(`/crm/connections/${connectionId}/dashboard/sales`),
    ])
      .then(([builderResponse, salesResponse]) => {
        if (cancelled) return;
        const nextPages = normalizePages(builderResponse.pages);
        setBuilder(builderResponse);
        setPages(nextPages);
        setActivePageKey((current) => (nextPages.some((page) => page.page_key === current) ? current : nextPages[0].page_key));
        setWidgets(normalizeWidgets(builderResponse.widgets, nextPages[0].page_key));
        setShareUrl(builderResponse.share.share_url);
        setSales(salesResponse);
      })
      .catch(() => {
        if (!cancelled) {
          setBuilder(null);
          setPages(defaultPages);
          setWidgets([]);
          setSales(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connectionId]);

  const widgetCatalog = builder?.widget_catalog?.length ? builder.widget_catalog : fallbackCatalog;
  const templateCatalog = builder?.dashboard_templates?.length ? builder.dashboard_templates : fallbackTemplates;
  const pageWidgets = useMemo(
    () => widgets.filter((widget) => widgetPageKey(widget, pages[0]?.page_key ?? 'main') === activePageKey),
    [activePageKey, pages, widgets],
  );
  const layouts = useMemo(
    () => ({
      lg: pageWidgets.map((widget) => ({
        i: widget.widget_key,
        x: widget.x,
        y: widget.y,
        w: widget.w,
        h: widget.h,
        minW: 2,
        minH: 2,
      })),
    }),
    [pageWidgets],
  );
  const groupedCatalog = useMemo(() => {
    const query = catalogSearch.trim().toLowerCase();
    return widgetCatalog
      .filter((item) => availabilityFilter === 'all' || (item.availability ?? 'available') === availabilityFilter)
      .filter((item) => !query || item.title.toLowerCase().includes(query) || item.widget_type.includes(query))
      .reduce<Record<string, CatalogItem[]>>((acc, item) => {
        const group = item.group || 'kpi';
        acc[group] = [...(acc[group] ?? []), item];
        return acc;
      }, {});
  }, [availabilityFilter, catalogSearch, widgetCatalog]);

  function applyLayout(layout: Layout[]) {
    setWidgets((current) =>
      current.map((widget) => {
        if (widgetPageKey(widget, pages[0]?.page_key ?? 'main') !== activePageKey) return widget;
        const next = layout.find((item) => item.i === widget.widget_key);
        return next
          ? { ...widget, x: next.x, y: next.y, w: next.w, h: next.h }
          : widget;
      }),
    );
  }

  function addWidget(type: DashboardWidgetType) {
    const catalogItem = widgetCatalog.find((item) => item.widget_type === type) ?? fallbackCatalog[0];
    const nextY = pageWidgets.reduce((max, widget) => Math.max(max, widget.y + widget.h), 0);
    const widget: DashboardWidget = {
      widget_key: `${type}-${Date.now().toString(36)}`,
      widget_type: type,
      title: catalogItem.title,
      x: 0,
      y: nextY,
      w: catalogItem.w,
      h: catalogItem.h,
      config: {
        page_key: activePageKey,
        availability: catalogItem.availability ?? 'available',
        requirements: catalogItem.requirements ?? [],
      },
    };
    setWidgets((current) => [...current, widget]);
  }

  function applyDashboardTemplate(template: DashboardTemplate) {
    const additions = template.widgets.map((type, index) => {
      const catalogItem = widgetCatalog.find((item) => item.widget_type === type) ?? fallbackCatalog[0];
      return {
        widget_key: `${type}-${Date.now().toString(36)}-${index}`,
        widget_type: type,
        title: catalogItem.title,
        x: (index % 2) * 6,
        y: Math.floor(index / 2) * catalogItem.h,
        w: Math.min(12, catalogItem.w),
        h: catalogItem.h,
        config: {
          page_key: activePageKey,
          availability: catalogItem.availability ?? 'available',
          requirements: catalogItem.requirements ?? [],
          template_key: template.template_key,
        },
      } satisfies DashboardWidget;
    });
    setWidgets((current) => [
      ...current.filter((widget) => widgetPageKey(widget, pages[0]?.page_key ?? 'main') !== activePageKey),
      ...additions,
    ]);
    setMessage(`Шаблон “${template.title}” применён к текущей странице`);
  }

  function addTemplate(template: (typeof quickTemplates)[number]) {
    const nextY = pageWidgets.reduce((max, widget) => Math.max(max, widget.y + widget.h), 0);
    const additions = template.widgets.map((type, index) => {
      const catalogItem = widgetCatalog.find((item) => item.widget_type === type) ?? fallbackCatalog[0];
      return {
        widget_key: `${type}-${Date.now().toString(36)}-${index}`,
        widget_type: type,
        title: catalogItem.title,
        x: (index % 2) * 6,
        y: nextY + Math.floor(index / 2) * catalogItem.h,
        w: Math.min(12, catalogItem.w),
        h: catalogItem.h,
        config: {
          page_key: activePageKey,
          availability: catalogItem.availability ?? 'available',
          requirements: catalogItem.requirements ?? [],
        },
      } satisfies DashboardWidget;
    });
    setWidgets((current) => [...current, ...additions]);
  }

  function removeWidget(widgetKey: string) {
    setWidgets((current) => current.filter((widget) => widget.widget_key !== widgetKey));
  }

  function addPage() {
    setPages((current) => {
      const pageKey = uniquePageKey(current, 'page');
      const next = [...current, { page_key: pageKey, title: `Страница ${current.length + 1}` }];
      setActivePageKey(pageKey);
      return next;
    });
  }

  function renameActivePage(title: string) {
    const cleanTitle = title.trim().slice(0, 80);
    setPages((current) =>
      current.map((page) => (page.page_key === activePageKey ? { ...page, title: cleanTitle || page.title } : page)),
    );
  }

  function deleteActivePage() {
    if (pages.length <= 1) {
      setMessage('Нельзя удалить последнюю страницу');
      return;
    }
    const activePageTitle = activePage?.title ?? 'страницу';
    if (pageWidgets.length > 0) {
      const confirmed = window.confirm(
        `Удалить страницу “${activePageTitle}” и все виджеты на ней: ${pageWidgets.length}?`,
      );
      if (!confirmed) return;
    }
    const activeIndex = pages.findIndex((page) => page.page_key === activePageKey);
    const nextPages = pages.filter((page) => page.page_key !== activePageKey);
    setPages(nextPages);
    setWidgets((current) =>
      current.filter((widget) => widgetPageKey(widget, pages[0]?.page_key ?? 'main') !== activePageKey),
    );
    setActivePageKey(nextPages[Math.max(0, activeIndex - 1)]?.page_key ?? nextPages[0].page_key);
    setMessage('Страница удалена. Нажмите “Сохранить”, чтобы применить изменения.');
  }

  function moveActivePage(direction: -1 | 1) {
    const index = pages.findIndex((page) => page.page_key === activePageKey);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= pages.length) return;
    const nextPages = [...pages];
    const [page] = nextPages.splice(index, 1);
    nextPages.splice(nextIndex, 0, page);
    setPages(nextPages);
  }

  async function saveDashboard() {
    if (!connectionId || !builder) return;
    setSaving(true);
    setMessage(null);
    try {
      const response = await api.put<DashboardBuilderPayload>(
        `/crm/connections/${connectionId}/dashboard-builder`,
        {
          name: builder.dashboard.name,
          filters: builder.dashboard.filters,
          pages,
          widgets,
        },
      );
      const nextPages = normalizePages(response.pages);
      setBuilder(response);
      setPages(nextPages);
      setActivePageKey((current) => (nextPages.some((page) => page.page_key === current) ? current : nextPages[0].page_key));
      setWidgets(normalizeWidgets(response.widgets, nextPages[0].page_key));
      setMessage('Дашборд сохранён');
    } catch {
      setMessage('Не удалось сохранить дашборд');
    } finally {
      setSaving(false);
    }
  }

  async function createShare() {
    if (!connectionId) return;
    setSaving(true);
    setMessage(null);
    try {
      const response = await api.post<DashboardBuilderPayload>(
        `/crm/connections/${connectionId}/dashboard-builder/share`,
      );
      setBuilder(response);
      setPages(normalizePages(response.pages));
      setShareUrl(response.share.share_url);
      setMessage('Embed-ссылка создана');
    } catch {
      setMessage('Не удалось создать embed-ссылку');
    } finally {
      setSaving(false);
    }
  }

  async function revokeShare() {
    if (!connectionId) return;
    setSaving(true);
    setMessage(null);
    try {
      const response = await api.post<DashboardBuilderPayload>(
        `/crm/connections/${connectionId}/dashboard-builder/share/revoke`,
      );
      setBuilder(response);
      setPages(normalizePages(response.pages));
      setShareUrl(null);
      setMessage('Embed-ссылка отозвана');
    } catch {
      setMessage('Не удалось отозвать embed-ссылку');
    } finally {
      setSaving(false);
    }
  }

  async function copyShare() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setMessage('Ссылка скопирована');
    } catch {
      setMessage(shareUrl);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-[620px]" />
      </div>
    );
  }

  if (!builder) {
    return <EmptyState title="Конструктор дашборда недоступен" />;
  }

  const activePage = pages.find((page) => page.page_key === activePageKey) ?? pages[0];

  return (
    <div className="space-y-5 pb-10">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-sm font-medium text-blue-700">CODE9 Analytics</div>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal text-slate-950">
              Конструктор дашборда
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Несколько страниц, безопасные виджеты и read-only embed-ссылка для amoCRM.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={saveDashboard}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              <Save className="h-4 w-4" />
              Сохранить
            </button>
            <button
              type="button"
              onClick={createShare}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
            >
              <Eye className="h-4 w-4" />
              Embed-ссылка
            </button>
            <button
              type="button"
              onClick={revokeShare}
              disabled={saving || !builder.share.enabled}
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              Отозвать
            </button>
          </div>
        </div>
        {shareUrl ? (
          <div className="mt-4 flex flex-col gap-2 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm sm:flex-row sm:items-center">
            <input
              value={shareUrl}
              readOnly
              className="min-w-0 flex-1 rounded-md border border-blue-100 bg-white px-3 py-2 text-slate-700"
            />
            <button
              type="button"
              onClick={copyShare}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-blue-600 px-3 py-2 font-medium text-white"
            >
              <Copy className="h-4 w-4" />
              Скопировать
            </button>
          </div>
        ) : null}
        {message ? <div className="mt-3 text-sm text-slate-600">{message}</div> : null}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-soft">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {pages.map((page) => (
              <button
                key={page.page_key}
                type="button"
                onClick={() => setActivePageKey(page.page_key)}
                className={cn(
                  'rounded-md px-3 py-2 text-sm font-medium',
                  page.page_key === activePageKey
                    ? 'bg-blue-600 text-white'
                    : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                )}
              >
                {page.title}
              </button>
            ))}
            <button
              type="button"
              onClick={addPage}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <Plus className="h-4 w-4" />
              Страница
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={activePage?.title ?? ''}
              onChange={(event) => renameActivePage(event.target.value)}
              className="w-52 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800"
              aria-label="Название страницы"
            />
            <button
              type="button"
              onClick={() => moveActivePage(-1)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50"
              aria-label="Передвинуть страницу влево"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => moveActivePage(1)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50"
              aria-label="Передвинуть страницу вправо"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={deleteActivePage}
              disabled={pages.length <= 1}
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              Удалить
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Готовые страницы</div>
          <div className="mt-3 space-y-2">
            {templateCatalog.map((template) => (
              <button
                key={template.template_key}
                type="button"
                onClick={() => applyDashboardTemplate(template)}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-800 hover:border-blue-200 hover:bg-blue-50"
              >
                <span className="block">{template.title}</span>
                <span className="mt-1 block text-xs font-normal text-slate-500">
                  {(template.widgets ?? []).length} блоков
                  {template.requirements?.length ? ` · нужна настройка: ${template.requirements.length}` : ''}
                </span>
              </button>
            ))}
          </div>

          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Быстрые шаблоны</div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {quickTemplates.map((template) => (
              <button
                key={template.title}
                type="button"
                onClick={() => addTemplate(template)}
                className="rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-800 hover:border-blue-200 hover:bg-blue-50"
              >
                {template.title}
              </button>
            ))}
          </div>

          <div className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">Виджеты</div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            {[
              ['all', 'Все'],
              ['available', 'Доступно'],
              ['requires_mapping', 'Поля'],
              ['requires_integration', 'Интеграции'],
              ['requires_ai', 'AI'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setAvailabilityFilter(key as typeof availabilityFilter)}
                className={cn(
                  'rounded-md border px-2 py-2 font-medium',
                  availabilityFilter === key
                    ? 'border-blue-600 bg-blue-50 text-blue-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="mt-3 flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-500">
            <Search className="h-4 w-4" />
            <input
              value={catalogSearch}
              onChange={(event) => setCatalogSearch(event.target.value)}
              placeholder="Поиск"
              className="min-w-0 flex-1 bg-transparent text-slate-800 outline-none placeholder:text-slate-400"
            />
          </label>
          <div className="mt-4 space-y-4">
            {Object.entries(groupedCatalog).map(([group, items]) => (
              <div key={group}>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {groupLabels[group] ?? group}
                </div>
                <div className="space-y-2">
                  {items.map((item) => (
                    <button
                      key={item.widget_type}
                      type="button"
                      onClick={() => addWidget(item.widget_type)}
                      className="flex w-full items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-800 hover:border-blue-200 hover:bg-blue-50"
                    >
                      <span>
                        <span className="block">{item.title}</span>
                        {item.availability && item.availability !== 'available' ? (
                          <span className="mt-1 block text-xs font-normal text-slate-500">
                            {availabilityLabel(item.availability)}
                          </span>
                        ) : null}
                      </span>
                      <Plus className="h-4 w-4 text-blue-600" />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3">
          {pageWidgets.length ? (
            <ResponsiveGridLayout
              className="layout"
              layouts={layouts}
              breakpoints={{ lg: 1100, md: 820, sm: 560, xs: 0 }}
              cols={{ lg: 12, md: 8, sm: 4, xs: 2 }}
              rowHeight={88}
              margin={[12, 12]}
              containerPadding={[0, 0]}
              draggableHandle=".dashboard-builder-drag"
              onLayoutChange={applyLayout}
              resizeHandles={['se']}
              compactType="vertical"
            >
              {pageWidgets.map((widget) => (
                <div key={widget.widget_key} className="group min-h-0">
                  <div className="relative h-full">
                    <div className="dashboard-builder-drag absolute left-3 top-3 z-10 h-6 w-10 cursor-move rounded-md border border-slate-200 bg-white/90 text-center text-xs leading-6 text-slate-400 opacity-0 shadow-sm transition group-hover:opacity-100">
                      ::
                    </div>
                    <button
                      type="button"
                      onClick={() => removeWidget(widget.widget_key)}
                      className={cn(
                        'absolute right-3 top-3 z-10 inline-flex h-7 w-7 items-center justify-center rounded-md',
                        'border border-slate-200 bg-white/90 text-slate-500 opacity-0 shadow-sm transition hover:text-rose-600 group-hover:opacity-100',
                      )}
                      aria-label="Удалить виджет"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <DashboardWidgetRenderer widget={widget} sales={sales} locale={locale} />
                  </div>
                </div>
              ))}
            </ResponsiveGridLayout>
          ) : (
            <div className="flex min-h-[420px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-sm text-slate-500">
              Добавьте виджет на страницу “{activePage?.title ?? 'Дашборд'}”
            </div>
          )}
        </main>
      </section>
    </div>
  );
}

function normalizePages(rawPages?: DashboardPage[]) {
  return rawPages?.length ? rawPages : defaultPages;
}

function normalizeWidgets(rawWidgets: DashboardWidget[], fallbackPageKey: string) {
  return rawWidgets.map((widget) => ({
    ...widget,
    config: {
      ...(widget.config ?? {}),
      page_key: widgetPageKey(widget, fallbackPageKey),
    },
  }));
}

function widgetPageKey(widget: DashboardWidget, fallbackPageKey: string) {
  const pageKey = widget.config?.page_key;
  return typeof pageKey === 'string' && pageKey ? pageKey : fallbackPageKey;
}

function uniquePageKey(pages: DashboardPage[], prefix: string) {
  let index = pages.length + 1;
  let key = `${prefix}-${index}`;
  const existing = new Set(pages.map((page) => page.page_key));
  while (existing.has(key)) {
    index += 1;
    key = `${prefix}-${index}`;
  }
  return key;
}

function availabilityLabel(value: string) {
  if (value === 'requires_mapping') return 'Нужно настроить поле';
  if (value === 'requires_integration') return 'Нужно подключить интеграцию';
  if (value === 'requires_ai') return 'Нужно включить AI-анализ';
  return 'Доступно';
}

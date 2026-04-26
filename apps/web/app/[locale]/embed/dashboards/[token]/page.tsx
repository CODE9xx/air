'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { DashboardWidgetRenderer } from '@/components/dashboard-builder/DashboardWidgetRenderer';
import type { DashboardBuilderPayload, DashboardPage, DashboardWidget } from '@/components/dashboard-builder/types';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

const defaultPage: DashboardPage = { page_key: 'main', title: 'Основная' };

export default function EmbedDashboardPage() {
  const params = useParams<{ token: string; locale: string }>();
  const token = params?.token;
  const locale = params?.locale ?? 'ru';
  const [payload, setPayload] = useState<DashboardBuilderPayload | null>(null);
  const [activePageKey, setActivePageKey] = useState(defaultPage.page_key);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .get<DashboardBuilderPayload>(`/dashboard-shares/${token}`, { scope: 'public' })
      .then((response) => {
        if (!cancelled) {
          const nextPages = normalizePages(response.pages);
          setPayload(response);
          setActivePageKey(nextPages[0].page_key);
        }
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const pages = useMemo(() => normalizePages(payload?.pages), [payload?.pages]);
  const pageWidgets = useMemo(
    () => [...(payload?.widgets ?? [])].sort((a, b) => a.y - b.y || a.x - b.x),
    [payload?.widgets],
  );
  const widgets = useMemo(
    () => pageWidgets.filter((widget) => widgetPageKey(widget, pages[0]?.page_key ?? defaultPage.page_key) === activePageKey),
    [activePageKey, pageWidgets, pages],
  );

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50 p-3">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-40 animate-pulse rounded-lg bg-white" />
          ))}
        </div>
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600">
          Дашборд недоступен
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 p-3">
      <div className="mb-3 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-blue-700">CODE9 Analytics</div>
          <h1 className="text-base font-semibold tracking-normal text-slate-950">{payload.dashboard.name}</h1>
        </div>
        <div className="text-xs text-slate-500">read-only</div>
      </div>
      {pages.length > 1 ? (
        <nav className="mb-3 flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2">
          {pages.map((page) => (
            <button
              key={page.page_key}
              type="button"
              onClick={() => setActivePageKey(page.page_key)}
              className={cn(
                'rounded-md px-3 py-2 text-sm font-medium',
                page.page_key === activePageKey
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-700 hover:bg-slate-50',
              )}
            >
              {page.title}
            </button>
          ))}
        </nav>
      ) : null}
      <section className="grid auto-rows-[88px] grid-cols-12 gap-3">
        {widgets.map((widget) => (
          <div
            key={widget.widget_key}
            className="min-h-0"
            style={{
              gridColumn: `span ${Math.min(12, Math.max(2, widget.w))}`,
              gridRow: `span ${Math.min(12, Math.max(2, widget.h))}`,
            }}
          >
            <DashboardWidgetRenderer widget={widget} sales={payload.sales ?? null} locale={locale} compact />
          </div>
        ))}
      </section>
    </main>
  );
}

function normalizePages(rawPages?: DashboardPage[]) {
  return rawPages?.length ? rawPages : [defaultPage];
}

function widgetPageKey(widget: DashboardWidget, fallbackPageKey: string) {
  const pageKey = widget.config?.page_key;
  return typeof pageKey === 'string' && pageKey ? pageKey : fallbackPageKey;
}

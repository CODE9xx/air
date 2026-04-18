'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { AuditResultCards } from '@/components/cabinet/AuditResultCard';
import { api } from '@/lib/api';
import type { AuditReport, AuditResultSummary } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { formatMoney, formatNumber } from '@/lib/utils';

export default function AuditPage() {
  const t = useTranslations('cabinet.audit');
  const tCommon = useTranslations('common');
  const params = useParams<{ id: string }>();
  const locale = useLocale();
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';
  const { toast } = useToast();

  const [summary, setSummary] = useState<AuditResultSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const res = await api.post<{ job_id: string }>(`/workspaces/${wsId}/audit/reports`, {
        crm_connection_id: params?.id,
        period: 'last_90_days',
      });
      // Имитация прогресса — в mock job сразу succeeded.
      await new Promise((r) => setTimeout(r, 900));
      // Попробуем получить последний отчёт.
      const list = await api.get<AuditReport[]>(`/workspaces/${wsId}/audit/reports`);
      const latest = list[list.length - 1];
      if (latest) setSummary(latest.summary);
      else {
        // fallback
        const r = await api.get<AuditReport>(`/workspaces/${wsId}/audit/reports/${res.job_id}`);
        setSummary(r.summary);
      }
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <Button onClick={run} loading={loading}>{t('run')}</Button>
      </header>

      {loading && (
        <div className="card p-10 flex items-center justify-center gap-3 text-sm text-muted-foreground">
          <Spinner size={20} />
          {t('running')}
        </div>
      )}

      {!loading && !summary && <EmptyState title={t('empty')} />}

      {!loading && summary && (
        <div className="space-y-6">
          <AuditResultCards summary={summary} locale={locale} />
          <div className="card p-5">
            <div className="font-semibold">{t('estimateTitle')}</div>
            <div className="mt-3 grid md:grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-xs text-muted-foreground">{t('estimateTime')}</div>
                <div className="mt-1 font-semibold">{formatNumber(summary.estimated_export_minutes, locale)} {t('minutes')}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">{t('estimatePrice')}</div>
                <div className="mt-1 font-semibold">{formatMoney(summary.estimated_price_rub * 100, 'RUB', locale)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">{t('storage')}</div>
                <div className="mt-1 font-semibold">{formatNumber(summary.estimated_storage_mb, locale)}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate, formatNumber } from '@/lib/utils';
import type { User } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { useToast } from '@/components/ui/Toast';

const PLAN_OPTIONS = [
  { key: 'free', label: 'Free', monthlyTokens: 0 },
  { key: 'paygo', label: 'Pay as you go', monthlyTokens: 0 },
  { key: 'start', label: 'Start', monthlyTokens: 3000 },
  { key: 'team', label: 'Team', monthlyTokens: 9000 },
  { key: 'pro', label: 'Pro', monthlyTokens: 18000 },
  { key: 'enterprise', label: 'Enterprise', monthlyTokens: 50000 },
];

interface AdminWorkspace {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string | null;
  owner_email: string | null;
  owner_name: string | null;
  plan: string;
  connections: number;
  active_connections: number;
  error_connections: number;
  balance_tokens: number;
  available_tokens: number;
  reserved_tokens: number;
  subscription_expires_at: string | null;
  last_error: string | null;
}

interface ImpersonateResponse {
  access_token: string;
  user: User & {
    support_mode?: {
      active: boolean;
      support_session_id: string;
      admin_email: string;
      reason: string;
      expires_at: string;
    };
  };
}

export default function AdminWorkspacesPage() {
  const t = useTranslations('admin.workspaces');
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();
  const { setUser, setAccessToken } = useUserAuth();
  const [items, setItems] = useState<AdminWorkspace[]>([]);
  const [enteringId, setEnteringId] = useState<string | null>(null);
  const [editingWorkspace, setEditingWorkspace] = useState<AdminWorkspace | null>(null);
  const [manualPlan, setManualPlan] = useState('enterprise');
  const [manualMonths, setManualMonths] = useState('12');
  const [manualExpiresAt, setManualExpiresAt] = useState('');
  const [manualTokens, setManualTokens] = useState('0');
  const [manualReason, setManualReason] = useState('Ручное назначение тарифа и токенов');
  const [savingBilling, setSavingBilling] = useState(false);

  const loadWorkspaces = async () => {
    const res = await api.get<{ items: AdminWorkspace[] }>('/admin/workspaces', { scope: 'admin' });
    setItems(res.items ?? []);
  };

  useEffect(() => {
    void loadWorkspaces();
  }, []);

  const openManualBilling = (workspace: AdminWorkspace) => {
    setEditingWorkspace(workspace);
    setManualPlan(workspace.plan || 'enterprise');
    setManualMonths('12');
    setManualExpiresAt('');
    setManualTokens('0');
    setManualReason(`Ручная настройка тарифа: ${workspace.owner_email ?? workspace.name}`);
  };

  const saveManualBilling = async () => {
    if (!editingWorkspace) return;
    setSavingBilling(true);
    try {
      const tokenAmount = Math.max(0, Number.parseInt(manualTokens || '0', 10) || 0);
      const periodMonths = manualExpiresAt
        ? 0
        : Math.max(0, Number.parseInt(manualMonths || '0', 10) || 0);
      await api.post(
        `/admin/workspaces/${editingWorkspace.id}/manual-billing`,
        {
          plan_key: manualPlan,
          period_months: periodMonths,
          expires_at: manualExpiresAt ? new Date(`${manualExpiresAt}T23:59:59`).toISOString() : null,
          add_tokens: tokenAmount,
          reason: manualReason.trim() || 'Ручная настройка тарифа и токенов',
        },
        { scope: 'admin' },
      );
      toast({ kind: 'success', title: 'Тариф и токены обновлены' });
      setEditingWorkspace(null);
      await loadWorkspaces();
    } catch {
      toast({ kind: 'error', title: 'Не удалось обновить тариф и токены' });
    } finally {
      setSavingBilling(false);
    }
  };

  const enterClient = async (workspace: AdminWorkspace) => {
    setEnteringId(workspace.id);
    try {
      const res = await api.post<ImpersonateResponse>(
        '/admin/support-mode/impersonate',
        {
          workspace_id: workspace.id,
          reason: `Founder support: ${workspace.owner_email ?? workspace.name}`,
        },
        { scope: 'admin' },
      );
      setAccessToken(res.access_token);
      setUser(res.user);
      if (typeof window !== 'undefined' && res.user.support_mode) {
        window.sessionStorage.setItem('code9_support_mode', JSON.stringify(res.user.support_mode));
      }
      router.push(`/${locale}/app`);
    } catch {
      toast({ kind: 'error', title: t('impersonateError') });
    } finally {
      setEnteringId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2">{t('name')}</th>
              <th className="px-4 py-2">{t('owner')}</th>
              <th className="px-4 py-2">{t('status')}</th>
              <th className="px-4 py-2">{t('plan')}</th>
              <th className="px-4 py-2 text-right">{t('tokens')}</th>
              <th className="px-4 py-2 text-right">{t('connections')}</th>
              <th className="px-4 py-2">{t('lastError')}</th>
              <th className="px-4 py-2 text-right">{t('actions')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.id} className="border-t border-border">
                <td className="px-4 py-3">
                  <div className="font-medium">{w.name}</div>
                  <div className="text-xs text-muted-foreground">{w.slug} · {formatDate(w.created_at, locale)}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium">{w.owner_email ?? '—'}</div>
                  <div className="text-xs text-muted-foreground">{w.owner_name ?? '—'}</div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={w.status === 'active' ? 'success' : 'neutral'}>{w.status}</Badge>
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium">{w.plan}</div>
                  <div className="text-xs text-muted-foreground">
                    до {formatDate(w.subscription_expires_at, locale)}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="font-semibold">{formatNumber(w.available_tokens, locale)}</div>
                  <div className="text-xs text-muted-foreground">
                    {formatNumber(w.reserved_tokens, locale)} {t('reserved')}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="font-semibold">{formatNumber(w.active_connections, locale)} / {formatNumber(w.connections, locale)}</div>
                  {w.error_connections > 0 && (
                    <div className="text-xs text-danger">{formatNumber(w.error_connections, locale)} {t('errors')}</div>
                  )}
                </td>
                <td className="max-w-[260px] px-4 py-3 text-xs text-muted-foreground">
                  {w.last_error ?? '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => openManualBilling(w)}
                    >
                      Тариф/токены
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={enteringId === w.id}
                      onClick={() => enterClient(w)}
                    >
                      {t('enterClient')}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog
        open={Boolean(editingWorkspace)}
        onClose={() => setEditingWorkspace(null)}
        title="Ручной тариф и AIC9-токены"
        className="max-w-2xl"
      >
        {editingWorkspace && (
          <div className="space-y-5">
            <div className="rounded-md border border-border bg-muted/50 p-4 text-sm">
              <div className="font-semibold">{editingWorkspace.name}</div>
              <div className="text-muted-foreground">
                {editingWorkspace.owner_email ?? 'email не указан'} · сейчас {editingWorkspace.plan}
              </div>
              <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <span>Доступно: {formatNumber(editingWorkspace.available_tokens, locale)}</span>
                <span>В резерве: {formatNumber(editingWorkspace.reserved_tokens, locale)}</span>
                <span>Срок: {formatDate(editingWorkspace.subscription_expires_at, locale)}</span>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="font-medium">Тариф</span>
                <select
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={manualPlan}
                  onChange={(event) => setManualPlan(event.target.value)}
                >
                  {PLAN_OPTIONS.map((plan) => (
                    <option key={plan.key} value={plan.key}>
                      {plan.label} · {formatNumber(plan.monthlyTokens, locale)} токенов/мес
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-1 text-sm">
                <span className="font-medium">Срок</span>
                <select
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={manualMonths}
                  onChange={(event) => setManualMonths(event.target.value)}
                  disabled={Boolean(manualExpiresAt)}
                >
                  <option value="0">Не менять дату</option>
                  <option value="1">1 месяц</option>
                  <option value="3">3 месяца</option>
                  <option value="6">6 месяцев</option>
                  <option value="12">12 месяцев</option>
                  <option value="24">24 месяца</option>
                  <option value="48">48 месяцев</option>
                </select>
              </label>

              <label className="space-y-1 text-sm">
                <span className="font-medium">Дата окончания вручную</span>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  type="date"
                  value={manualExpiresAt}
                  onChange={(event) => setManualExpiresAt(event.target.value)}
                />
              </label>

              <label className="space-y-1 text-sm">
                <span className="font-medium">Начислить токенов</span>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  min={0}
                  step={1000}
                  type="number"
                  value={manualTokens}
                  onChange={(event) => setManualTokens(event.target.value)}
                />
              </label>
            </div>

            <label className="space-y-1 text-sm">
              <span className="font-medium">Причина</span>
              <textarea
                className="min-h-[88px] w-full rounded-md border border-border bg-background px-3 py-2"
                value={manualReason}
                onChange={(event) => setManualReason(event.target.value)}
              />
            </label>

            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Это ручная админская операция без реального платежа. Начисление токенов попадёт в ledger,
              смена тарифа и срока попадёт в admin audit log.
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditingWorkspace(null)}>
                Отмена
              </Button>
              <Button loading={savingBilling} onClick={saveManualBilling}>
                Сохранить
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}

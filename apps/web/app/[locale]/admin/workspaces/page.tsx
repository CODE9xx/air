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
import { useToast } from '@/components/ui/Toast';

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

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: AdminWorkspace[] }>('/admin/workspaces', { scope: 'admin' });
      setItems(res.items ?? []);
    })();
  }, []);

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
                <td className="px-4 py-3">{w.plan}</td>
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
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={enteringId === w.id}
                    onClick={() => enterClient(w)}
                  >
                    {t('enterClient')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { Notification } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';

export function NotificationsList({ workspaceId }: { workspaceId: string }) {
  const t = useTranslations('cabinet.notifications');
  const locale = useLocale();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get<Notification[]>(`/workspaces/${workspaceId}/notifications`);
        setItems(res);
      } finally {
        setLoading(false);
      }
    })();
  }, [workspaceId]);

  const markRead = async (id: string) => {
    await api.post(`/workspaces/${workspaceId}/notifications/${id}/read`);
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }
  if (!items.length) return <EmptyState title={t('empty')} />;

  return (
    <ul className="space-y-2">
      {items.map((n) => (
        <li key={n.id} className="card p-4 flex items-start justify-between gap-4">
          <div>
            <div className="font-medium">{n.title}</div>
            {n.body && <p className="text-sm text-muted-foreground mt-1">{n.body}</p>}
            <div className="text-xs text-muted-foreground mt-2">{formatDate(n.created_at, locale)}</div>
          </div>
          {!n.read_at && (
            <button onClick={() => markRead(n.id)} className="text-xs text-primary hover:underline whitespace-nowrap">
              {t('markRead')}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

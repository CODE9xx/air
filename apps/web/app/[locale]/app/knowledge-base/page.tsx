'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { useUserAuth } from '@/components/providers/AuthProvider';

interface KnowledgeItem {
  id: string;
  title: string;
  body: string;
}

export default function KnowledgeBasePage() {
  const t = useTranslations('cabinet.knowledgeBase');
  const tConnections = useTranslations('cabinet.connections');
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const [items, setItems] = useState<KnowledgeItem[]>([]);

  useEffect(() => {
    if (!wsId) return;
    (async () => {
      try {
        const res = await api.get<KnowledgeItem[]>(`/workspaces/${wsId}/ai/knowledge`);
        setItems(res);
      } catch {
        setItems([]);
      }
    })();
  }, [wsId]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <Button variant="secondary" disabled={!wsId}>{t('addManual')}</Button>
      </header>
      {!wsId ? (
        <EmptyState title={tConnections('noWorkspaceTitle')} description={tConnections('noWorkspaceBody')} />
      ) : items.length === 0 ? (
        <EmptyState title={t('empty')} />
      ) : (
        <ul className="space-y-2">
          {items.map((i) => (
            <li key={i.id} className="card p-4">
              <div className="font-medium">{i.title}</div>
              <p className="text-sm text-muted-foreground mt-1">{i.body}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

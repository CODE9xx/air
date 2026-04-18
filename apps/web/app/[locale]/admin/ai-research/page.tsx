'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { EmptyState } from '@/components/ui/EmptyState';

interface Pattern {
  id: string;
  title: string;
  count: number;
}

export default function AdminAIResearchPage() {
  const t = useTranslations('admin.aiResearch');
  const [items, setItems] = useState<Pattern[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: Pattern[] }>('/admin/ai/research-patterns', { scope: 'admin' });
      setItems(res.items ?? []);
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      {items.length === 0 ? (
        <EmptyState title={t('empty')} />
      ) : (
        <ul className="space-y-2">
          {items.map((p) => (
            <li key={p.id} className="card p-4 flex items-center justify-between">
              <div className="font-medium">{p.title}</div>
              <div className="text-sm text-muted-foreground">{p.count}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

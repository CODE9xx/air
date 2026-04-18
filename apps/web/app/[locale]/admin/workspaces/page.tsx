'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { api } from '@/lib/api';

interface AdminWorkspace {
  id: string;
  name: string;
  slug: string;
  status: string;
  plan: string;
  connections: number;
}

export default function AdminWorkspacesPage() {
  const t = useTranslations('admin.workspaces');
  const [items, setItems] = useState<AdminWorkspace[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: AdminWorkspace[] }>('/admin/workspaces', { scope: 'admin' });
      setItems(res.items ?? []);
    })();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2">{t('name')}</th>
              <th className="px-4 py-2">{t('slug')}</th>
              <th className="px-4 py-2">{t('status')}</th>
              <th className="px-4 py-2">{t('plan')}</th>
              <th className="px-4 py-2 text-right">{t('connections')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.id} className="border-t border-border">
                <td className="px-4 py-2 font-medium">{w.name}</td>
                <td className="px-4 py-2 text-muted-foreground">{w.slug}</td>
                <td className="px-4 py-2">{w.status}</td>
                <td className="px-4 py-2">{w.plan}</td>
                <td className="px-4 py-2 text-right">{w.connections}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

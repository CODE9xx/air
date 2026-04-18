'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { Badge } from '@/components/ui/Badge';

export default function AdminConnectionsPage() {
  const t = useTranslations('admin.connections');
  const locale = useLocale();
  const [items, setItems] = useState<CrmConnection[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: CrmConnection[] }>('/admin/connections', { scope: 'admin' });
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
              <th className="px-4 py-2">{t('provider')}</th>
              <th className="px-4 py-2">{t('status')}</th>
              <th className="px-4 py-2">id</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-border">
                <td className="px-4 py-2 font-medium capitalize">{c.provider}</td>
                <td className="px-4 py-2">
                  <Badge>{c.status}</Badge>
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  <Link href={`/${locale}/admin/connections/${c.id}`} className="text-primary hover:underline">
                    {c.id}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

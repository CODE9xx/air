'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/utils';

interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

export default function AdminUsersPage() {
  const t = useTranslations('admin.users');
  const locale = useLocale();
  const [items, setItems] = useState<AdminUser[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: AdminUser[] }>('/admin/users', { scope: 'admin' });
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
              <th className="px-4 py-2">{t('email')}</th>
              <th className="px-4 py-2">{t('name')}</th>
              <th className="px-4 py-2">{t('createdAt')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} className="border-t border-border">
                <td className="px-4 py-2 font-medium">{u.email}</td>
                <td className="px-4 py-2">{u.display_name ?? '—'}</td>
                <td className="px-4 py-2 text-muted-foreground">{formatDate(u.created_at, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/utils';

interface AuditLog {
  id: string;
  admin_user_id: string;
  action: string;
  target: string;
  created_at: string;
}

export default function AdminAuditLogsPage() {
  const t = useTranslations('admin.auditLogs');
  const locale = useLocale();
  const [items, setItems] = useState<AuditLog[]>([]);

  useEffect(() => {
    (async () => {
      const res = await api.get<{ items: AuditLog[] }>('/admin/audit-logs', { scope: 'admin' });
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
              <th className="px-4 py-2">{t('createdAt')}</th>
              <th className="px-4 py-2">{t('admin')}</th>
              <th className="px-4 py-2">{t('action')}</th>
              <th className="px-4 py-2">{t('target')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((l) => (
              <tr key={l.id} className="border-t border-border">
                <td className="px-4 py-2 text-muted-foreground">{formatDate(l.created_at, locale)}</td>
                <td className="px-4 py-2">{l.admin_user_id}</td>
                <td className="px-4 py-2 font-medium">{l.action}</td>
                <td className="px-4 py-2">{l.target}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

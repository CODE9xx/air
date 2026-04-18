'use client';

import { useTranslations, useLocale } from 'next-intl';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { BillingAccount, BillingLedgerEntry } from '@/lib/types';
import { formatDate, formatMoney } from '@/lib/utils';
import { Skeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';

export function BillingPanel({ workspaceId }: { workspaceId: string }) {
  const t = useTranslations('cabinet.billing');
  const locale = useLocale();
  const { toast } = useToast();
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [ledger, setLedger] = useState<BillingLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [a, l] = await Promise.all([
          api.get<BillingAccount>(`/workspaces/${workspaceId}/billing/account`),
          api.get<{ items: BillingLedgerEntry[] }>(`/workspaces/${workspaceId}/billing/ledger`),
        ]);
        setAccount(a);
        setLedger(l.items ?? []);
      } finally {
        setLoading(false);
      }
    })();
  }, [workspaceId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (!account) return null;

  return (
    <div className="space-y-6">
      <div className="card p-6 flex items-center justify-between">
        <div>
          <div className="text-sm text-muted-foreground">{t('balance')}</div>
          <div className="mt-1 text-3xl font-semibold">{formatMoney(account.balance_cents, account.currency, locale)}</div>
          <div className="mt-2 text-xs text-muted-foreground">{t('plan')}: {account.plan}</div>
        </div>
        <Button onClick={() => toast({ kind: 'info', title: t('topUp') })}>{t('topUp')}</Button>
      </div>
      <div className="card">
        <div className="p-5 border-b border-border font-semibold">{t('history')}</div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground bg-muted">
            <tr>
              <th className="px-5 py-2">{t('date')}</th>
              <th className="px-5 py-2">{t('description')}</th>
              <th className="px-5 py-2 text-right">{t('amount')}</th>
            </tr>
          </thead>
          <tbody>
            {ledger.map((e) => (
              <tr key={e.id} className="border-t border-border">
                <td className="px-5 py-2">{formatDate(e.created_at, locale)}</td>
                <td className="px-5 py-2">{e.description}</td>
                <td className={`px-5 py-2 text-right font-medium ${e.amount_cents < 0 ? 'text-danger' : 'text-success'}`}>
                  {formatMoney(e.amount_cents, e.currency, locale)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

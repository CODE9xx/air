'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/Badge';
import type { CrmConnection } from '@/lib/types';
import { formatDate } from '@/lib/utils';

const statusToTone: Record<string, 'success' | 'warning' | 'danger' | 'neutral' | 'info'> = {
  active: 'success',
  pending: 'info',
  paused: 'warning',
  failed: 'danger',
  deleting: 'warning',
  deleted: 'neutral',
};

export function ConnectionCard({ conn }: { conn: CrmConnection }) {
  const t = useTranslations('cabinet.connections');
  const locale = useLocale();
  return (
    <Link
      href={`/${locale}/app/connections/${conn.id}`}
      className="card p-5 block hover:border-primary transition"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-block h-8 w-8 rounded bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center">
            {conn.provider.slice(0, 2).toUpperCase()}
          </span>
          <div>
            <div className="font-semibold capitalize">{conn.provider}</div>
            <div className="text-xs text-muted-foreground">{conn.external_domain ?? '—'}</div>
          </div>
        </div>
        <Badge tone={statusToTone[conn.status] ?? 'neutral'}>
          {t(
            `status${conn.status.charAt(0).toUpperCase()}${conn.status.slice(1)}` as
              | 'statusActive'
              | 'statusPending'
              | 'statusPaused'
              | 'statusFailed'
              | 'statusDeleting'
              | 'statusDeleted',
          )}
        </Badge>
      </div>
      <dl className="mt-4 space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between">
          <dt>{t('lastSync')}</dt>
          <dd>{formatDate(conn.last_sync_at, locale)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>{t('tokenExpires')}</dt>
          <dd>{formatDate(conn.token_expires_at, locale)}</dd>
        </div>
      </dl>
    </Link>
  );
}

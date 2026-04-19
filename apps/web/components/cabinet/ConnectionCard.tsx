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

/**
 * Возвращает строку свежести токена: ok / soon / expired.
 * «soon» — если истекает в ближайшие 24 часа.
 */
function tokenFreshness(iso?: string | null): 'ok' | 'soon' | 'expired' | null {
  if (!iso) return null;
  const expiresAt = new Date(iso).getTime();
  if (Number.isNaN(expiresAt)) return null;
  const now = Date.now();
  if (expiresAt <= now) return 'expired';
  if (expiresAt - now < 24 * 60 * 60 * 1000) return 'soon';
  return 'ok';
}

export function ConnectionCard({ conn }: { conn: CrmConnection }) {
  const t = useTranslations('cabinet.connections');
  const locale = useLocale();

  const amo = conn.metadata?.amo_account;
  const isMock = Boolean(conn.metadata?.mock);
  // Предпочитаем человекочитаемое имя аккаунта amoCRM, если есть.
  const headline = amo?.name ?? conn.name ?? null;
  const subdomain = amo?.subdomain ?? conn.external_domain ?? null;
  const freshness = tokenFreshness(conn.token_expires_at);

  return (
    <Link
      href={`/${locale}/app/connections/${conn.id}`}
      className="card p-5 block hover:border-primary transition"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-block h-8 w-8 rounded bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center shrink-0">
            {conn.provider.slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <div className="font-semibold capitalize truncate">
              {headline ?? conn.provider}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              {subdomain ?? '—'}
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
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
          {isMock && (
            <Badge tone="neutral" className="text-[10px]">
              {t('mockBadge')}
            </Badge>
          )}
        </div>
      </div>
      <dl className="mt-4 space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between">
          <dt>{t('lastSync')}</dt>
          <dd>{formatDate(conn.last_sync_at, locale)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>{t('tokenExpires')}</dt>
          <dd className="flex items-center gap-1">
            {formatDate(conn.token_expires_at, locale)}
            {freshness === 'soon' && (
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" aria-label={t('tokenSoon')} />
            )}
            {freshness === 'expired' && (
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500" aria-label={t('tokenExpired')} />
            )}
          </dd>
        </div>
        {conn.last_error && (
          <div className="flex justify-between text-red-600 dark:text-red-400">
            <dt className="truncate pr-2">{t('lastError')}</dt>
            <dd className="truncate max-w-[55%]" title={conn.last_error}>
              {conn.last_error}
            </dd>
          </div>
        )}
      </dl>
    </Link>
  );
}

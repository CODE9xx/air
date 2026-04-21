'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { ConnectionCard } from '@/components/cabinet/ConnectionCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

/**
 * Флаги OAuth-колбэка, которые может присылать backend.
 * См. apps/api/app/crm/oauth_router.py → `_ui_redirect(...)`.
 */
type OAuthFlash =
  | 'amocrm_connected'
  | 'amocrm_bad_referer'
  | 'amocrm_invalid_grant'
  | 'amocrm_exchange_failed'
  | 'amocrm_cancelled'
  | 'amocrm_credentials_missing'
  | 'mock_oauth_ok';

export default function ConnectionsPage() {
  const t = useTranslations('cabinet.connections');
  const tFlash = useTranslations('cabinet.connections.flash');
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, ready } = useUserAuth();
  const { toast } = useToast();
  // Task #52.4: НЕ подставляем синтетический 'ws-demo-1' fallback —
  // он приводил к запросу `/workspaces/ws-demo-1/crm/connections`, который
  // теперь (когда эндпойнт существует) отдал бы 422 Invalid UUID, а до
  // фикса — 404 Not Found. Берём реальный workspace_id из user.workspaces[0].id.
  // Три состояния:
  //   !ready            → /auth/me ещё не завершился → skeleton
  //   ready && !wsId    → user загружен, но нет workspace → empty state
  //   ready && wsId     → фетч connections
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const hasNoWorkspace = ready && !wsId;

  const [conns, setConns] = useState<CrmConnection[] | null>(null);
  const flashShown = useRef(false);

  useEffect(() => {
    if (!wsId) {
      // user ещё не подгрузился ИЛИ нет workspace — не дёргаем API.
      return;
    }
    (async () => {
      try {
        const res = await api.get<CrmConnection[]>(`/workspaces/${wsId}/crm/connections`);
        setConns(res);
      } catch {
        setConns([]);
      }
    })();
  }, [wsId]);

  // Показываем toast по OAuth-флагу и чистим query-string, чтобы не дублировался
  // при hot-reload / навигации назад.
  useEffect(() => {
    if (flashShown.current) return;
    const flash = searchParams?.get('flash') as OAuthFlash | null;
    if (!flash) return;
    flashShown.current = true;
    const flashToKind: Record<OAuthFlash, 'success' | 'error' | 'info'> = {
      amocrm_connected: 'success',
      mock_oauth_ok: 'success',
      amocrm_cancelled: 'info',
      amocrm_bad_referer: 'error',
      amocrm_invalid_grant: 'error',
      amocrm_exchange_failed: 'error',
      amocrm_credentials_missing: 'error',
    };
    toast({
      kind: flashToKind[flash] ?? 'info',
      title: tFlash(flash),
    });
    // cleanup: убираем ?flash=... из URL
    const url = new URL(window.location.href);
    url.searchParams.delete('flash');
    router.replace(url.pathname + (url.search ? url.search : ''));
  }, [searchParams, toast, tFlash, router]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <Link
          href={`/${locale}/app/connections/new`}
          className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
        >
          {t('addNew')}
        </Link>
      </header>

      {/* 1) /auth/me ещё не завершился — skeleton */}
      {!ready && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      )}

      {/* 2) user загружен, но нет workspace — empty state без кнопки
           «Подключить CRM», т.к. подключаться некому. */}
      {hasNoWorkspace && (
        <EmptyState
          title={t('noWorkspaceTitle')}
          description={t('noWorkspaceBody')}
        />
      )}

      {/* 3) wsId есть, но connections ещё не получены — skeleton */}
      {ready && wsId && conns === null && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      )}

      {/* 4) получили [] — standard empty state с CTA */}
      {ready && wsId && conns !== null && conns.length === 0 && (
        <EmptyState
          title={t('emptyTitle')}
          description={t('emptyBody')}
          action={
            <Link
              href={`/${locale}/app/connections/new`}
              className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-700"
            >
              {t('addFirst')}
            </Link>
          }
        />
      )}

      {/* 5) получили список — карточки */}
      {ready && wsId && conns !== null && conns.length > 0 && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {conns.map((c) => (
            <ConnectionCard key={c.id} conn={c} />
          ))}
        </div>
      )}
    </div>
  );
}

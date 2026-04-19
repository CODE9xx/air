'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { api, ApiError } from '@/lib/api';
import type { AmoOAuthStartResponse, CrmConnection } from '@/lib/types';
import { useToast } from '@/components/ui/Toast';
import { useUserAuth } from '@/components/providers/AuthProvider';

/**
 * Страница «Новое подключение».
 *
 * Два режима подключения amoCRM:
 *   — real OAuth (Phase 2A): `GET /integrations/amocrm/oauth/start?workspace_id`
 *     → редирект на amoCRM. Если сервер отвечает 501 (mock-только), показываем
 *     toast и оставляем пользователя на странице.
 *   — mock (legacy): `POST /crm/connections/mock-amocrm`. Остаётся для demo/dev
 *     стенда; в prod (`MOCK_CRM_MODE=false`) ручка не скрыта, но работает как
 *     запрос к реальному OAuth через BE.
 */
export default function NewConnectionPage() {
  const t = useTranslations('cabinet.connections.new');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';

  const [loadingOAuth, setLoadingOAuth] = useState(false);
  const [loadingMock, setLoadingMock] = useState(false);

  const connectOAuth = async () => {
    setLoadingOAuth(true);
    try {
      const res = await api.get<AmoOAuthStartResponse>(
        '/integrations/amocrm/oauth/start',
        { query: { workspace_id: wsId } },
      );
      // Mock-режим: BE уже создал active подключение, идём сразу в карточку.
      if (res.mock && res.redirect_url) {
        router.push(res.redirect_url);
        return;
      }
      // Real: редирект на amoCRM consent-screen.
      if (res.authorize_url) {
        window.location.assign(res.authorize_url);
        return;
      }
      toast({ kind: 'error', title: tCommon('error') });
      setLoadingOAuth(false);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.message
          ? err.message
          : t('oauthError');
      toast({ kind: 'error', title: msg });
      setLoadingOAuth(false);
    }
  };

  const connectMock = async () => {
    setLoadingMock(true);
    try {
      const res = await api.post<CrmConnection>(
        '/crm/connections/mock-amocrm',
        { name: 'amoCRM (mock)' },
      );
      router.push(`/${locale}/app/connections/${res.id}`);
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
      setLoadingMock(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="card p-5 flex flex-col">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-primary/10 text-primary font-semibold">
            am
          </div>
          <h3 className="mt-3 font-semibold">{t('amocrm')}</h3>
          <p className="text-xs text-muted-foreground mt-1 flex-1">
            {t('amocrmDesc')}
          </p>
          <div className="mt-4 flex flex-col gap-2">
            <Button onClick={connectOAuth} loading={loadingOAuth}>
              {t('connectOAuth')}
            </Button>
            <Button
              variant="secondary"
              onClick={connectMock}
              loading={loadingMock}
            >
              {t('connectMock')}
            </Button>
          </div>
        </div>

        <div className="card p-5 opacity-80">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-muted text-muted-foreground font-semibold">
            ko
          </div>
          <h3 className="mt-3 font-semibold">Kommo</h3>
          <p className="text-xs text-muted-foreground mt-1">{t('kommoDesc')}</p>
          <Badge tone="neutral" className="mt-4">
            {tCommon('comingSoon')}
          </Badge>
        </div>

        <div className="card p-5 opacity-80">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-muted text-muted-foreground font-semibold">
            bx
          </div>
          <h3 className="mt-3 font-semibold">Bitrix24</h3>
          <p className="text-xs text-muted-foreground mt-1">
            {t('bitrixDesc')}
          </p>
          <Badge tone="neutral" className="mt-4">
            {tCommon('comingSoon')}
          </Badge>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{t('oauthNote')}</p>
    </div>
  );
}

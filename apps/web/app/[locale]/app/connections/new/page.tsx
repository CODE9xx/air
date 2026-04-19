'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { api, ApiError } from '@/lib/api';
import type {
  AmoButtonConfig,
  AmoOAuthStartResponse,
  CrmConnection,
} from '@/lib/types';
import { useToast } from '@/components/ui/Toast';
import { useUserAuth } from '@/components/providers/AuthProvider';

/**
 * Страница «Новое подключение».
 *
 * Три режима подключения amoCRM:
 *   — mock (legacy): кнопка «mock» создаёт фейковое подключение через
 *     `POST /crm/connections/mock-amocrm`. Остаётся для demo/dev.
 *   — real OAuth (static_client): `GET /integrations/amocrm/oauth/start`
 *     возвращает `authorize_url` → редиректим юзера на amoCRM consent.
 *   — real OAuth (external_button, #44.6): `start` создаёт pending
 *     CrmConnection и возвращает `state + redirect_uri`. Фронт переадресует
 *     юзера на marketplace-страницу amoCRM (со state в URL); amoCRM сама
 *     создаёт интеграцию в момент клика и присылает credentials webhook'ом.
 *     Юзера amoCRM возвращает на наш /oauth/callback.
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
  const [buttonConfig, setButtonConfig] = useState<AmoButtonConfig | null>(null);

  // Подгружаем конфиг кнопки один раз при mount'е, чтобы понимать,
  // какой режим бэкенд ожидает, и показать клиенту соответствующую
  // подсказку (особенно про webhook для external_button).
  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.get<AmoButtonConfig>(
          '/integrations/amocrm/oauth/button-config',
        );
        setButtonConfig(cfg);
      } catch {
        // Без конфига кнопка всё равно работает в дефолтном static_client
        // режиме — тихо игнорируем.
      }
    })();
  }, []);

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
      // Real, static_client: редирект на amoCRM consent-screen.
      if (res.auth_mode === 'static_client' || res.authorize_url) {
        if (res.authorize_url) {
          window.location.assign(res.authorize_url);
          return;
        }
      }
      // Real, external_button (#44.6): authorize_url НЕ приходит — фронт
      // переадресует юзера на marketplace-страницу amoCRM, где он жмёт
      // «Установить». amoCRM пришлёт нам credentials webhook'ом и
      // вернёт юзера на /oauth/callback.
      if (res.auth_mode === 'external_button' && res.connection_id) {
        // В нашем минимально-инвазивном варианте отправляем юзера на
        // карточку pending-подключения; backend дождётся credentials
        // и активирует connection при первом callback'е amoCRM.
        // (Полноценный embedded button widget — следующий итерационный шаг.)
        toast({
          kind: 'info',
          title: t('externalButtonInstruction'),
          description: t('externalButtonHint'),
        });
        router.push(`/${locale}/app/connections/${res.connection_id}`);
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

      {buttonConfig?.auth_mode === 'external_button' && !buttonConfig.mock && (
        <div className="card p-4 text-xs text-muted-foreground border-primary/30">
          <div className="font-semibold text-foreground mb-1">
            {t('externalButtonModeTitle')}
          </div>
          <p>{t('externalButtonModeDesc')}</p>
          {(buttonConfig.secrets_uri ?? buttonConfig.webhook_url) && (
            <p className="mt-2 font-mono break-all">
              {t('externalButtonWebhookLabel')}:{' '}
              {buttonConfig.secrets_uri ?? buttonConfig.webhook_url}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

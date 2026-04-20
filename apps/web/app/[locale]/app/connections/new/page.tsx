'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
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
import { AmoCrmExternalButton } from '@/components/integrations/AmoCrmExternalButton';

/**
 * Страница «Новое подключение».
 *
 * Три режима подключения amoCRM:
 *   — mock (legacy): кнопка «mock» создаёт фейковое подключение через
 *     `POST /crm/connections/mock-amocrm`. Остаётся для demo/dev.
 *   — real OAuth (static_client): `GET /integrations/amocrm/oauth/start`
 *     возвращает `authorize_url` → редиректим юзера на amoCRM consent.
 *   — real OAuth (external_button, #44.6 v3 / #51.1):
 *     шаг 1 — клик Code9 → `GET /oauth/start` создаёт pending CrmConnection
 *              и state в Redis (TTL 600s), возвращает
 *              {auth_mode, connection_id, state, redirect_uri}.
 *     шаг 2 — фронт рендерит официальный amoCRM widget
 *              (`<script class="amocrm_oauth">`) со state и secrets_uri
 *              из /button-config; юзер подтверждает установку в amoCRM,
 *              amoCRM шлёт POST /external/secrets и редиректит юзера на
 *              /oauth/callback, бэк активирует connection.
 *     Фронт НЕ редиректит юзера на /connections/<id> до срабатывания
 *     callback'а — иначе amoCRM никогда не получит наш data-state.
 */

interface ExternalButtonStart {
  state: string;
  redirectUri: string;
  /**
   * Внутреннее — не показывается в UI (Task #51.1 требует не светить
   * connection_id в production UI). Храним только для диагностики /
   * чтобы backend мог привязать callback к правильной connection.
   */
  connectionId: string;
}

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
  const [externalStart, setExternalStart] = useState<ExternalButtonStart | null>(
    null,
  );

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
      if (res.authorize_url) {
        window.location.assign(res.authorize_url);
        return;
      }
      // Real, external_button (#51.1): authorize_url НЕ приходит; вместо
      // redirect'а переключаем UI на шаг 2 и рендерим amoCRM widget
      // ниже. amoCRM пришлёт нам POST /external/secrets и вернёт юзера
      // на /oauth/callback.
      if (
        res.auth_mode === 'external_button' &&
        res.state &&
        res.redirect_uri &&
        res.connection_id
      ) {
        setExternalStart({
          state: res.state,
          redirectUri: res.redirect_uri,
          connectionId: res.connection_id,
        });
        setLoadingOAuth(false);
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

  const resetExternalFlow = () => {
    setExternalStart(null);
  };

  const handleWidgetDenied = useCallback(
    (reason?: unknown) => {
      // amoCRM вызвал error-callback — пользователь отказал или возник
      // сетевой сбой. Секреты в `reason` не приходят (только строка/код),
      // но для надёжности всё равно приводим к строке без логирования
      // полного объекта.
      const msg =
        typeof reason === 'string'
          ? reason
          : reason && typeof reason === 'object' && 'message' in reason
            ? String((reason as { message?: unknown }).message ?? '')
            : '';
      toast({
        kind: 'warning',
        title: t('externalButtonDenied'),
        description: msg || undefined,
      });
    },
    [t, toast],
  );

  const isExternalButtonMode =
    buttonConfig?.auth_mode === 'external_button' && !buttonConfig.mock;

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      {externalStart && isExternalButtonMode && buttonConfig ? (
        <section className="card p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">
              {t('externalButtonStepTitle')}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {t('externalButtonStepHint')}
            </p>
          </div>
          <AmoCrmExternalButton
            state={externalStart.state}
            redirectUri={externalStart.redirectUri}
            buttonConfig={buttonConfig}
            onDenied={handleWidgetDenied}
          />
          <div>
            <Button variant="secondary" onClick={resetExternalFlow}>
              {tCommon('back')}
            </Button>
          </div>
        </section>
      ) : (
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
            <p className="text-xs text-muted-foreground mt-1">
              {t('kommoDesc')}
            </p>
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
      )}

      <p className="text-xs text-muted-foreground">{t('oauthNote')}</p>

      {isExternalButtonMode && !externalStart && (
        <div className="card p-4 text-xs text-muted-foreground border-primary/30">
          <div className="font-semibold text-foreground mb-1">
            {t('externalButtonModeTitle')}
          </div>
          <p>{t('externalButtonModeDesc')}</p>
          {(buttonConfig?.secrets_uri ?? buttonConfig?.webhook_url) && (
            <p className="mt-2 font-mono break-all">
              {t('externalButtonWebhookLabel')}:{' '}
              {buttonConfig?.secrets_uri ?? buttonConfig?.webhook_url}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

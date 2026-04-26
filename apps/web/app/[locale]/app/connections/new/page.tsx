'use client';

import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
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
 *     шаг 1 — клик CODE9 → `GET /oauth/start` создаёт pending CrmConnection
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
  const { user, ready } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;

  const [loadingOAuth, setLoadingOAuth] = useState(false);
  const [loadingMock, setLoadingMock] = useState(false);
  const [buttonConfig, setButtonConfig] = useState<AmoButtonConfig | null>(null);
  const [externalStart, setExternalStart] = useState<ExternalButtonStart | null>(
    null,
  );
  const [existingConnections, setExistingConnections] = useState<CrmConnection[]>(
    [],
  );
  const [checkingExisting, setCheckingExisting] = useState(false);

  const existingCrmConnection =
    existingConnections.find((connection) => connection.status !== 'deleted') ??
    null;
  const canRetryExistingOAuth =
    existingCrmConnection?.provider === 'amocrm' &&
    ['pending', 'failed'].includes(existingCrmConnection.status);
  const blocksNewCrm = Boolean(existingCrmConnection) && !canRetryExistingOAuth;

  // Подгружаем конфиг кнопки один раз при mount'е, чтобы понимать,
  // какой режим бэкенд ожидает.
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

  useEffect(() => {
    if (!wsId) {
      setExistingConnections([]);
      setCheckingExisting(false);
      return;
    }
    let cancelled = false;
    setCheckingExisting(true);
    (async () => {
      try {
        const rows = await api.get<CrmConnection[]>(
          `/workspaces/${wsId}/crm/connections`,
        );
        if (!cancelled) setExistingConnections(rows);
      } catch {
        if (!cancelled) setExistingConnections([]);
      } finally {
        if (!cancelled) setCheckingExisting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [wsId]);

  const openExistingConnection = useCallback(() => {
    if (!existingCrmConnection) return;
    router.push(`/${locale}/app/connections/${existingCrmConnection.id}`);
  }, [existingCrmConnection, locale, router]);

  const connectOAuth = async () => {
    if (!wsId) {
      toast({ kind: 'error', title: tCommon('error') });
      return;
    }
    if (blocksNewCrm) {
      toast({ kind: 'info', title: t('singleCrmConflict') });
      openExistingConnection();
      return;
    }
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
      if (err instanceof ApiError && err.code === 'crm_connection_exists') {
        toast({ kind: 'info', title: t('singleCrmConflict') });
        setLoadingOAuth(false);
        return;
      }
      const msg =
        err instanceof ApiError && err.message
          ? err.message
          : t('oauthError');
      toast({ kind: 'error', title: msg });
      setLoadingOAuth(false);
    }
  };

  const connectMock = async () => {
    if (!wsId) {
      toast({ kind: 'error', title: tCommon('error') });
      return;
    }
    if (blocksNewCrm) {
      toast({ kind: 'info', title: t('singleCrmConflict') });
      openExistingConnection();
      return;
    }
    setLoadingMock(true);
    try {
      const res = await api.post<CrmConnection>(
        '/crm/connections/mock-amocrm',
        { name: 'amoCRM (mock)' },
      );
      router.push(`/${locale}/app/connections/${res.id}`);
    } catch (err) {
      const title =
        err instanceof ApiError && err.code === 'crm_connection_exists'
          ? t('singleCrmConflict')
          : tCommon('error');
      toast({
        kind:
          err instanceof ApiError && err.code === 'crm_connection_exists'
            ? 'info'
            : 'error',
        title,
      });
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
    <div className="space-y-6 max-w-5xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      {existingCrmConnection && (
        <section className="card border-primary/30 bg-primary/5 p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <Badge tone="success">{t('singleCrmBadge')}</Badge>
              <h2 className="mt-3 text-lg font-semibold">
                {t('singleCrmTitle')}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('singleCrmBody')}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-md border border-border bg-background px-2 py-1">
                  {existingCrmConnection.provider}
                </span>
                <span className="rounded-md border border-border bg-background px-2 py-1">
                  {existingCrmConnection.name ?? t('amocrm')}
                </span>
                <span className="rounded-md border border-border bg-background px-2 py-1">
                  {existingCrmConnection.status}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {canRetryExistingOAuth && (
                <Button onClick={connectOAuth} loading={loadingOAuth}>
                  {t('singleCrmContinue')}
                </Button>
              )}
              <Button variant="secondary" onClick={openExistingConnection}>
                {t('singleCrmOpen')}
              </Button>
            </div>
          </div>
        </section>
      )}

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
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="card p-4 flex flex-col items-center text-center">
            <IntegrationLogo
              src="/amocrm-wordmark.png"
              alt="amoCRM"
            />
            <h3 className="mt-3 font-semibold">{t('amocrm')}</h3>
            <p className="text-xs text-muted-foreground mt-1 flex-1">
              {t('amocrmDesc')}
            </p>
            <div className="mt-4 flex w-full flex-col gap-2">
              <Button
                onClick={connectOAuth}
                loading={loadingOAuth}
                disabled={
                  !ready ||
                  !wsId ||
                  checkingExisting ||
                  blocksNewCrm
                }
              >
                {t('connectOAuth')}
              </Button>
              <Button
                variant="secondary"
                onClick={connectMock}
                loading={loadingMock}
                disabled={
                  !ready ||
                  !wsId ||
                  checkingExisting ||
                  blocksNewCrm ||
                  canRetryExistingOAuth
                }
              >
                {t('connectMock')}
              </Button>
              {blocksNewCrm && (
                <p className="text-xs text-muted-foreground">
                  {t('singleCrmHint')}
                </p>
              )}
            </div>
          </div>

          <div className="card p-4 flex flex-col items-center text-center border-primary/30 bg-primary/5">
            <IntegrationLogo src="/email-wordmark.svg" alt={t('email')} />
            <h3 className="mt-3 font-semibold">{t('email')}</h3>
            <p className="text-xs text-muted-foreground mt-1 flex-1">
              {t('emailDesc')}
            </p>
            <Link
              href={`/${locale}/app/connections/email`}
              className="mt-4 inline-flex w-full items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-700"
            >
              {t('configureEmail')}
            </Link>
          </div>

          <div className="card p-4 flex flex-col items-center text-center opacity-80">
            <IntegrationLogo
              src="/kommo-wordmark.svg"
              alt="Kommo"
            />
            <h3 className="mt-3 font-semibold">Kommo</h3>
            <p className="text-xs text-muted-foreground mt-1">
              {t('kommoDesc')}
            </p>
            <Badge tone="neutral" className="mt-4">
              {tCommon('comingSoon')}
            </Badge>
          </div>

          <div className="card p-4 flex flex-col items-center text-center opacity-80">
            <IntegrationLogo
              src="/bitrix24-wordmark.svg"
              alt="Bitrix24"
            />
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

    </div>
  );
}

function IntegrationLogo({
  src,
  alt,
}: {
  src: string;
  alt: string;
}) {
  return (
    <div className="flex h-36 w-full items-center justify-center rounded-lg border border-border bg-white px-4 py-4 shadow-sm md:h-40">
      <img
        src={src}
        alt={alt}
        className="max-h-28 w-full max-w-[310px] object-contain object-center md:max-h-32"
        loading="lazy"
      />
    </div>
  );
}

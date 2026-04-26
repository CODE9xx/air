'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/Button';
import type { AmoButtonConfig } from '@/lib/types';

/**
 * AmoCrmExternalButton (#51.1) — встраиваемый amoCRM OAuth widget.
 *
 * Task #44.6 v3 (external_button режим):
 *   - Рендерит официальный `<script class="amocrm_oauth">` (button.min.js)
 *     клиент-сайд. SSR запрещён: скрипт трогает window/document.
 *   - Обязательные data-* атрибуты:
 *     data-name, data-description, data-redirect_uri, data-secrets_uri,
 *     data-logo, data-scopes, data-title, data-compact, data-class-name,
 *     data-color, data-state, data-error-callback, data-mode.
 *   - `data-client-id` НЕ ставится: в external_button интеграцию создаёт
 *     amoCRM в момент клика и сама присылает client_id webhook-ом.
 *   - `data-state` берётся ТОЛЬКО из ответа `GET /oauth/start`
 *     (не из `GET /button-config` — там state не публикуется).
 *   - `data-secrets_uri` / redirect_uri / button metadata берутся из
 *     `GET /button-config`.
 *   - Никаких secrets в DOM: client_secret, access_token, refresh_token
 *     и authorization code в атрибуты/HTML не попадают.
 *
 * Widget script грузится максимум 5 секунд; по таймауту или `error`-событию
 * показываем localized ошибку + «Повторить». Ручного marketplace-fallback
 * без state нет (это разрушило бы state-binding).
 */

// amoCRM widget вызывает глобальную функцию из data-error-callback по имени,
// когда юзер отказал / возникла ошибка авторизации в popup. Объявляем
// optional-свойство на window, чтобы избежать `any`.
declare global {
  interface Window {
    code9AmoCrmOAuthError?: (reason?: unknown) => void;
  }
}

export interface AmoCrmExternalButtonProps {
  /** state из `GET /integrations/amocrm/oauth/start` (TTL 600s в Redis). */
  state: string;
  /** redirect_uri — точное значение, зарегистрированное в amoCRM-панели. */
  redirectUri: string;
  /** Публичная конфигурация кнопки (secrets_uri + button-metadata). */
  buttonConfig: AmoButtonConfig;
  /** Вызывается при error-callback от amoCRM (отказ / iframe-error). */
  onDenied?: (reason?: unknown) => void;
}

const WIDGET_SRC = 'https://www.amocrm.ru/auth/button.min.js';
const LOAD_TIMEOUT_MS = 5000;

type WidgetStatus = 'loading' | 'ready' | 'error';

export function AmoCrmExternalButton({
  state,
  redirectUri,
  buttonConfig,
  onDenied,
}: AmoCrmExternalButtonProps) {
  const t = useTranslations('cabinet.connections.new');
  const containerRef = useRef<HTMLDivElement>(null);
  const onDeniedRef = useRef(onDenied);
  const [status, setStatus] = useState<WidgetStatus>('loading');
  // reloadNonce меняется при retry — перезапускает useEffect.
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    onDeniedRef.current = onDenied;
  }, [onDenied]);

  const handleRetry = useCallback(() => {
    setStatus('loading');
    setReloadNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Primary по v2 — secrets_uri; webhook_url оставлен как legacy alias
    // и указывает на тот же URL на бэке. Если по какой-то причине оба
    // пустые — это config-error, виджет не запустится.
    const secretsUri = buttonConfig.secrets_uri ?? buttonConfig.webhook_url;
    if (!secretsUri || !state || !redirectUri) {
      setStatus('error');
      return;
    }

    // Чистим предыдущие попытки (retry), если были.
    container.innerHTML = '';

    const meta = buttonConfig.button ?? {};
    // Все дефолты должны совпадать с prod env (AMOCRM_BUTTON_*):
    // имя бренда пишем CODE9 в верхнем регистре, как на сайте и лендингах.
    // `dataLogo` — ABSOLUTE URL на публичный CODE9 asset 400x272,
    // как требует форма amoCRM marketplace.
    // amoCRM marketplace загружает эту картинку при
    // установке интеграции и показывает её в «Установленных»; относительный
    // путь у них не раскрывается, поэтому собираем через `location.origin`.
    const dataName = meta.name ?? 'CODE9 Analytics';
    const dataDescription =
      meta.description ??
      'AI-аналитика и аудит продаж и коммуникаций в amoCRM';
    const dataScopes = meta.scopes ?? 'crm,notifications';
    const dataTitle = meta.title ?? 'Подключить amoCRM';
    const dataLogo = meta.logo ?? `${window.location.origin}/code9-amocrm-marketplace-400x272.png`;

    const script = document.createElement('script');
    script.className = 'amocrm_oauth';
    script.src = WIDGET_SRC;
    script.setAttribute('charset', 'utf-8');
    script.setAttribute('data-name', dataName);
    script.setAttribute('data-description', dataDescription);
    script.setAttribute('data-redirect_uri', redirectUri);
    script.setAttribute('data-secrets_uri', secretsUri);
    if (dataLogo) script.setAttribute('data-logo', dataLogo);
    script.setAttribute('data-scopes', dataScopes);
    script.setAttribute('data-title', dataTitle);
    script.setAttribute('data-compact', 'false');
    script.setAttribute('data-class-name', 'code9-amocrm-oauth-button');
    script.setAttribute('data-color', 'blue');
    script.setAttribute('data-state', state);
    script.setAttribute('data-error-callback', 'code9AmoCrmOAuthError');
    script.setAttribute('data-mode', 'popup');
    // Ни при каких обстоятельствах:
    //   data-client-id   — в external_button режиме его быть не должно.
    //   client_secret / access_token / refresh_token / authorization code
    //   — секреты не попадают в DOM.

    // Регистрируем глобальный error-callback ДО appendChild, чтобы
    // widget-скрипт, если он исполнится синхронно, сразу нашёл функцию.
    window.code9AmoCrmOAuthError = (reason) => {
      onDeniedRef.current?.(reason);
    };

    let cancelled = false;
    const handleLoad = () => {
      if (cancelled) return;
      // amoCRM's button.min.js installs its button renderer as
      // `window.onload = function(){ ...render... }` — it assumes it
      // will be included in the initial HTML, so the window 'load'
      // event fires *after* evaluation and triggers the rendering.
      //
      // In our SPA we inject the script dynamically after user action,
      // long after 'load' has already fired. Re-assigning window.onload
      // at that point is a no-op (the event doesn't re-fire), so the
      // button never gets rendered despite the script loading 200 OK.
      //
      // Fix: manually invoke the handler that the widget just installed.
      // We guard against (a) non-function handlers (e.g., if amoCRM ever
      // ships a fix), and (b) handler throwing — the load event itself
      // succeeded, so we still set status='ready' to allow retry.
      try {
        const handler = window.onload;
        if (typeof handler === 'function') {
          handler.call(window, new Event('load'));
        }
      } catch {
        /* widget render threw; status='ready' still lets user retry */
      }
      setStatus('ready');
    };
    const handleError = () => {
      if (cancelled) return;
      setStatus('error');
    };

    script.addEventListener('load', handleLoad);
    script.addEventListener('error', handleError);

    const timeoutId = window.setTimeout(() => {
      if (cancelled) return;
      setStatus((current) => (current === 'loading' ? 'error' : current));
    }, LOAD_TIMEOUT_MS);

    container.appendChild(script);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      script.removeEventListener('load', handleLoad);
      script.removeEventListener('error', handleError);
      if (container.contains(script)) {
        container.removeChild(script);
      }
      if (window.code9AmoCrmOAuthError) {
        delete window.code9AmoCrmOAuthError;
      }
    };
    // reloadNonce — триггер для retry; onDenied читается через ref.
  }, [state, redirectUri, buttonConfig, reloadNonce]);

  return (
    <div className="space-y-3">
      {status === 'loading' && (
        <div
          data-testid="amocrm-widget-loading"
          className="text-xs text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          {t('externalButtonLoading')}
        </div>
      )}
      {status === 'error' && (
        <div
          data-testid="amocrm-widget-error"
          className="space-y-2"
          role="alert"
        >
          <p className="text-sm text-destructive">
            {t('externalButtonLoadError')}
          </p>
          <Button variant="secondary" onClick={handleRetry}>
            {t('externalButtonRetry')}
          </Button>
        </div>
      )}
      <div
        ref={containerRef}
        data-testid="amocrm-oauth-widget"
        className="amocrm-widget-slot"
      />
    </div>
  );
}

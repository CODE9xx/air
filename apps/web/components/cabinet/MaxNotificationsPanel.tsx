'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BellRing, Bot, CheckCircle2, Send, Settings2 } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';

const MAX_BOT_USERNAME = 'id860229601650_bot';
const MAX_BOT_URL = `https://max.ru/${MAX_BOT_USERNAME}`;
const CHANNEL_STORAGE_KEY = 'code9:notifications:max:enabled';

const settings = [
  'integrationErrors',
  'exportStatus',
  'dailyStats',
  'lowTokenBalance',
  'trialOrPlanEnding',
] as const;

type SettingKey = (typeof settings)[number];

const defaultSettings: Record<SettingKey, boolean> = {
  integrationErrors: true,
  exportStatus: true,
  dailyStats: false,
  lowTokenBalance: true,
  trialOrPlanEnding: true,
};

export function MaxNotificationsPanel() {
  const t = useTranslations('cabinet.notifications.max');
  const { toast } = useToast();
  const [enabled, setEnabled] = useState(defaultSettings);
  const [channelEnabled, setChannelEnabled] = useState(false);
  const connected = channelEnabled;

  useEffect(() => {
    const saved = window.localStorage.getItem(CHANNEL_STORAGE_KEY);
    if (saved) setChannelEnabled(saved === 'true');
  }, []);

  const toggle = (key: SettingKey) => {
    setEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleChannel = () => {
    setChannelEnabled((prev) => {
      const next = !prev;
      window.localStorage.setItem(CHANNEL_STORAGE_KEY, String(next));
      return next;
    });
  };

  const showPendingToast = (action: 'check' | 'test') => {
    toast({
      kind: 'info',
      title: action === 'check' ? t('checkDisabledTitle') : t('testDisabledTitle'),
      description: t('disabledBody'),
    });
  };

  return (
    <section className="card p-5 space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-cyan-500/10 text-cyan-600">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">{t('title')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={connected ? 'success' : 'neutral'}>
            {connected ? t('connected') : t('notConnected')}
          </Badge>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-md border border-border bg-background px-4 py-3">
        <div>
          <div className="text-sm font-medium">{t('channelToggleTitle')}</div>
          <p className="mt-1 text-xs text-muted-foreground">{t('channelToggleBody')}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={channelEnabled}
          onClick={toggleChannel}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 rounded-full border border-transparent transition focus:outline-none focus:ring-2 focus:ring-primary/40',
            channelEnabled ? 'bg-cyan-600' : 'bg-muted-foreground/30',
          )}
        >
          <span
            className={cn(
              'inline-block h-5 w-5 translate-y-0.5 rounded-full bg-white shadow transition',
              channelEnabled ? 'translate-x-5' : 'translate-x-0.5',
            )}
          />
        </button>
      </div>

      <div className="rounded-md border border-border bg-muted/60 p-4">
        <div className="flex items-start gap-3">
          <BellRing className="mt-0.5 h-5 w-5 text-cyan-600" />
          <div>
            <div className="font-medium">{t('commonBotTitle')}</div>
            <p className="mt-1 text-sm text-muted-foreground">{t('commonBotBody')}</p>
            <p className="mt-2 text-sm font-medium text-foreground">@{MAX_BOT_USERNAME}</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <a className="btn-primary" href={MAX_BOT_URL} target="_blank" rel="noreferrer">
          <Bot className="h-4 w-4" />
          {t('openBot')}
        </a>
        <Button type="button" variant="secondary" onClick={() => showPendingToast('check')}>
          <CheckCircle2 className="h-4 w-4" />
          {t('checkChat')}
        </Button>
        <Button type="button" variant="secondary" onClick={() => showPendingToast('test')}>
          <Send className="h-4 w-4" />
          {t('sendTest')}
        </Button>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          {t('settingsTitle')}
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {settings.map((key) => (
            <label
              key={key}
              className={cn(
                'flex items-start gap-3 rounded-md border border-border bg-white px-3 py-3 text-sm',
                !channelEnabled && 'opacity-60',
              )}
            >
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary/40"
                checked={enabled[key]}
                disabled={!channelEnabled}
                onChange={() => toggle(key)}
              />
              <span>
                <span className="block font-medium">{t(`settings.${key}.title`)}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{t(`settings.${key}.body`)}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{t('safeMode')}</p>
      </div>
    </section>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BellRing, Bot, CheckCircle2, Send, Settings2 } from 'lucide-react';
import { ApiError, api } from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';

const CHANNEL_STORAGE_KEY = 'code9:notifications:telegram:enabled';
const CHAT_STORAGE_KEY = 'code9:notifications:telegram:chat';
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

type TelegramBotMetadata = {
  configured: boolean;
  verified: boolean;
  username: string | null;
  url: string | null;
  start_parameter?: string | null;
};

type TelegramChat = {
  chat_id: number;
  chat_type: string;
  title: string | null;
  username: string | null;
};

type TelegramChatCheck = {
  connected: boolean;
  start_parameter: string;
  chat: TelegramChat | null;
};

type TelegramTestResponse = {
  ok: boolean;
  chat: TelegramChat;
};

export function TelegramNotificationsPanel() {
  const t = useTranslations('cabinet.notifications.telegram');
  const { toast } = useToast();
  const [enabled, setEnabled] = useState(defaultSettings);
  const [channelEnabled, setChannelEnabled] = useState(false);
  const [bot, setBot] = useState<TelegramBotMetadata | null>(null);
  const [botLoading, setBotLoading] = useState(true);
  const [chat, setChat] = useState<TelegramChat | null>(null);
  const [checkingChat, setCheckingChat] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);
  const botConfigured = Boolean(bot?.configured);
  const connected = channelEnabled;

  useEffect(() => {
    let cancelled = false;
    api
      .get<TelegramBotMetadata>('/integrations/telegram/bot')
      .then((metadata) => {
        if (!cancelled) setBot(metadata);
      })
      .catch(() => {
        if (!cancelled) setBot(null);
      })
      .finally(() => {
        if (!cancelled) setBotLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem(CHANNEL_STORAGE_KEY);
    if (saved) setChannelEnabled(saved === 'true');
    const savedChat = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (savedChat) {
      try {
        setChat(JSON.parse(savedChat) as TelegramChat);
      } catch {
        window.localStorage.removeItem(CHAT_STORAGE_KEY);
      }
    }
  }, []);

  const toggleChannel = () => {
    setChannelEnabled((prev) => {
      const next = !prev;
      window.localStorage.setItem(CHANNEL_STORAGE_KEY, String(next));
      if (!next) {
        window.localStorage.removeItem(CHAT_STORAGE_KEY);
        setChat(null);
      }
      return next;
    });
  };

  const markConnected = (nextChat: TelegramChat | null) => {
    setChannelEnabled(true);
    window.localStorage.setItem(CHANNEL_STORAGE_KEY, 'true');
    if (nextChat) {
      setChat(nextChat);
      window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(nextChat));
    }
  };

  const toggle = (key: SettingKey) => {
    setEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const checkChat = async () => {
    setCheckingChat(true);
    try {
      const result = await api.post<TelegramChatCheck>('/integrations/telegram/check-chat');
      if (result.connected) markConnected(result.chat);
      toast({
        kind: result.connected ? 'success' : 'warning',
        title: result.connected ? t('check.connectedTitle') : t('check.notFoundTitle'),
        description: result.connected
          ? formatChatLabel(result.chat)
          : t('check.notFoundBody', { code: result.start_parameter }),
      });
    } catch (error) {
      toast({
        kind: 'error',
        title: t('check.errorTitle'),
        description: error instanceof ApiError ? error.message : t('genericError'),
      });
    } finally {
      setCheckingChat(false);
    }
  };

  const sendTest = async () => {
    setSendingTest(true);
    try {
      const result = await api.post<TelegramTestResponse>('/integrations/telegram/send-test');
      markConnected(result.chat);
      toast({
        kind: 'success',
        title: t('test.sentTitle'),
        description: formatChatLabel(result.chat),
      });
    } catch (error) {
      toast({
        kind: 'error',
        title: t('test.errorTitle'),
        description: error instanceof ApiError ? error.message : t('genericError'),
      });
    } finally {
      setSendingTest(false);
    }
  };

  return (
    <section className="card p-5 space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
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
            channelEnabled ? 'bg-primary' : 'bg-muted-foreground/30',
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
          <BellRing className="mt-0.5 h-5 w-5 text-primary" />
          <div>
            <div className="font-medium">{t('commonBotTitle')}</div>
            <p className="mt-1 text-sm text-muted-foreground">{t('commonBotBody')}</p>
            {bot?.username && (
              <p className="mt-2 text-sm font-medium text-foreground">@{bot.username}</p>
            )}
            {bot?.start_parameter && (
              <p className="mt-2 text-xs text-muted-foreground">
                {t('connectCode')}: <code className="rounded bg-background px-1.5 py-0.5 text-foreground">{bot.start_parameter}</code>
              </p>
            )}
            {chat && (
              <p className="mt-1 text-xs text-success">
                {t('chatLinked')}: {formatChatLabel(chat)}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {bot?.url ? (
          <a
            className="btn-primary"
            href={bot.url}
            target="_blank"
            rel="noreferrer"
          >
            <Bot className="h-4 w-4" />
            {t('openBot')}
          </a>
        ) : (
          <Button type="button" disabled={botLoading}>
            <Bot className="h-4 w-4" />
            {t('openBot')}
          </Button>
        )}
        <Button
          type="button"
          variant="secondary"
          onClick={checkChat}
          loading={checkingChat}
          disabled={!botConfigured || botLoading}
        >
          <CheckCircle2 className="h-4 w-4" />
          {t('checkChat')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={sendTest}
          loading={sendingTest}
          disabled={!botConfigured || botLoading}
        >
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

function formatChatLabel(chat: TelegramChat | null): string {
  if (!chat) return '';
  if (chat.title) return chat.title;
  if (chat.username) return `@${chat.username}`;
  return `${chat.chat_type} ${chat.chat_id}`;
}

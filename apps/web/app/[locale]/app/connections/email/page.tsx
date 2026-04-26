'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useLocale } from 'next-intl';
import {
  AlertCircle,
  CheckCircle2,
  Inbox,
  KeyRound,
  Mail,
  PlayCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { api, ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';

type ProviderKey = 'gmail' | 'microsoft' | 'yandex' | 'imap';
type ScopeKey = 'crm_only' | 'all_mailbox';
type PeriodKey = 'last_12_months' | 'current_year' | 'all_time';

interface MailboxDraft {
  id: string;
  email: string;
  provider: ProviderKey;
  imapHost: string;
  imapPort: number;
  imapSsl: boolean;
  username: string;
  appPassword: string;
  folders: string;
}

interface EmailConnection {
  id: string;
  provider: ProviderKey;
  email_address: string;
  display_name?: string | null;
  imap_host: string;
  imap_port: number;
  imap_ssl: boolean;
  username: string;
  folders: string[];
  sync_scope: ScopeKey;
  period: PeriodKey;
  status: 'pending' | 'active' | 'paused' | 'error' | 'deleted';
  last_sync_at?: string | null;
  last_error?: string | null;
  last_counts?: {
    folders?: number;
    messages_seen?: number;
    messages_imported?: number;
    messages_skipped?: number;
    messages_failed?: number;
    bytes_seen?: number;
  };
}

interface JobCreated {
  job_id: string;
  rq_job_id?: string;
}

const providerDefaults: Record<ProviderKey, { label: string; host: string; port: number; ssl: boolean }> = {
  gmail: { label: 'Gmail / Google Workspace', host: 'imap.gmail.com', port: 993, ssl: true },
  microsoft: { label: 'Microsoft 365 / Outlook', host: 'outlook.office365.com', port: 993, ssl: true },
  yandex: { label: 'Yandex 360 / Яндекс Почта', host: 'imap.yandex.ru', port: 993, ssl: true },
  imap: { label: 'Другая почта IMAP', host: '', port: 993, ssl: true },
};

const periodLabels: Record<PeriodKey, string> = {
  last_12_months: 'Последние 12 месяцев',
  current_year: 'Текущий год',
  all_time: 'Весь период',
};

const scopeLabels: Record<ScopeKey, string> = {
  crm_only: 'Только письма, где есть email из amoCRM',
  all_mailbox: 'Вся выбранная почта за период',
};

const statusLabels: Record<EmailConnection['status'], string> = {
  pending: 'Ожидает проверки',
  active: 'Подключено',
  paused: 'На паузе',
  error: 'Ошибка',
  deleted: 'Удалено',
};

function emptyMailbox(id = `mailbox-${Date.now()}`): MailboxDraft {
  return {
    id,
    email: '',
    provider: 'gmail',
    imapHost: providerDefaults.gmail.host,
    imapPort: 993,
    imapSsl: true,
    username: '',
    appPassword: '',
    folders: 'INBOX',
  };
}

function splitFolders(value: string): string[] {
  const folders = value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return folders.length ? folders : ['INBOX'];
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return 'Не удалось выполнить действие';
}

export default function EmailConnectionPage() {
  const locale = useLocale();
  const { user, ready } = useUserAuth();
  const workspaceId = user?.workspaces?.[0]?.id ?? null;

  const [drafts, setDrafts] = useState<MailboxDraft[]>([emptyMailbox('mailbox-1')]);
  const [syncScope, setSyncScope] = useState<ScopeKey>('crm_only');
  const [period, setPeriod] = useState<PeriodKey>('last_12_months');
  const [connections, setConnections] = useState<EmailConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canUseApi = ready && Boolean(workspaceId);

  const filledDrafts = useMemo(
    () => drafts.filter((draft) => draft.email.trim() && draft.username.trim() && draft.appPassword.trim()),
    [drafts],
  );

  const loadConnections = async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const rows = await api.get<EmailConnection[]>(`/workspaces/${workspaceId}/email/connections`);
      setConnections(rows);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (workspaceId) void loadConnections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const updateDraft = (id: string, patch: Partial<MailboxDraft>) => {
    setDrafts((items) => items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
    setMessage(null);
    setError(null);
  };

  const updateProvider = (id: string, provider: ProviderKey) => {
    const defaults = providerDefaults[provider];
    setDrafts((items) =>
      items.map((item) =>
        item.id === id
          ? {
              ...item,
              provider,
              imapHost: defaults.host || item.imapHost,
              imapPort: defaults.port,
              imapSsl: defaults.ssl,
            }
          : item,
      ),
    );
    setMessage(null);
    setError(null);
  };

  const addMailbox = () => {
    setDrafts((items) => [...items, emptyMailbox(`mailbox-${Date.now()}-${items.length + 1}`)]);
  };

  const removeMailbox = (id: string) => {
    setDrafts((items) => (items.length > 1 ? items.filter((item) => item.id !== id) : items));
  };

  const saveMailboxes = async () => {
    if (!workspaceId || filledDrafts.length === 0) {
      setError('Заполните email, login и app password минимум для одного ящика.');
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      for (const draft of filledDrafts) {
        await api.post<EmailConnection>(`/workspaces/${workspaceId}/email/connections`, {
          provider: draft.provider,
          email_address: draft.email.trim(),
          display_name: draft.email.trim(),
          imap_host: draft.imapHost.trim(),
          imap_port: Number(draft.imapPort || 993),
          imap_ssl: draft.imapSsl,
          username: draft.username.trim(),
          app_password: draft.appPassword,
          folders: splitFolders(draft.folders),
          sync_scope: syncScope,
          period,
          test_connection: true,
        });
      }
      setDrafts((items) =>
        items.map((item) => (item.appPassword ? { ...item, appPassword: '' } : item)),
      );
      setMessage(`Подключено ящиков: ${filledDrafts.length}. Теперь можно запускать выгрузку.`);
      await loadConnections();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async (connectionId: string) => {
    setBusyId(connectionId);
    setError(null);
    setMessage(null);
    try {
      await api.post(`/email/connections/${connectionId}/test`);
      setMessage('Проверка прошла успешно.');
      await loadConnections();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusyId(null);
    }
  };

  const startExport = async (connection: EmailConnection) => {
    setBusyId(connection.id);
    setError(null);
    setMessage(null);
    try {
      const job = await api.post<JobCreated>(`/email/connections/${connection.id}/export`, {
        folders: connection.folders,
        period: connection.period,
      });
      setMessage(`Выгрузка почты поставлена в очередь. Job: ${job.job_id}`);
      await loadConnections();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <header className="cabinet-page-hero rounded-2xl border border-border p-6">
        <Link
          href={`/${locale}/app/connections/new`}
          className="text-sm font-medium text-primary hover:underline"
        >
          Назад к подключениям
        </Link>
        <div className="mt-5 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <Badge tone="info">IMAP-first боевой режим</Badge>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground">Подключение почты</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Можно подключить несколько ящиков клиента. CODE9 проверяет IMAP-доступ, шифрует app password
              на backend и запускает отдельную выгрузку по каждому ящику, чтобы один сбой не ломал остальные.
            </p>
          </div>
          <div className="rounded-xl border border-primary/20 bg-white/75 p-4 text-sm shadow-soft">
            <div className="flex items-center gap-2 font-semibold text-foreground">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Безопасный старт
            </div>
            <p className="mt-2 max-w-md text-xs leading-5 text-muted-foreground">
              Вложения не скачиваются, пароль не возвращается в API, по умолчанию сохраняются только письма,
              где найден email контакта или менеджера из amoCRM.
            </p>
          </div>
        </div>
      </header>

      {!ready ? (
        <section className="card p-5 text-sm text-muted-foreground">Загружаем аккаунт...</section>
      ) : !workspaceId ? (
        <section className="card border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
          Сначала нужен workspace. API не вызывается без реального workspace id.
        </section>
      ) : null}

      {message ? (
        <div className="flex items-start gap-2 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{message}</span>
        </div>
      ) : null}
      {error ? (
        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="card p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Mail className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold">Почтовые ящики</h2>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              Для Gmail, Яндекс и Microsoft в первом боевом варианте используйте app password и IMAP host.
              OAuth подключим отдельным этапом, когда будет отдельное согласование token storage.
            </p>
          </div>
          <Badge tone="neutral">Черновиков: {drafts.length}</Badge>
        </div>

        <div className="mt-5 grid gap-3">
          {drafts.map((draft, index) => (
            <div key={draft.id} className="rounded-xl border border-border bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-foreground">Ящик #{index + 1}</div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => removeMailbox(draft.id)}
                  disabled={drafts.length === 1}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Удалить
                </Button>
              </div>

              <div className="mt-4 grid gap-3 lg:grid-cols-4">
                <label className="block">
                  <span className="text-xs font-medium text-muted-foreground">Провайдер</span>
                  <select
                    value={draft.provider}
                    onChange={(event) => updateProvider(draft.id, event.target.value as ProviderKey)}
                    className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  >
                    {Object.entries(providerDefaults).map(([key, item]) => (
                      <option key={key} value={key}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <TextInput
                  label="Email ящика"
                  type="email"
                  value={draft.email}
                  placeholder="manager@company.ru"
                  onChange={(value) => updateDraft(draft.id, { email: value, username: draft.username || value })}
                />
                <TextInput
                  label="IMAP host"
                  value={draft.imapHost}
                  placeholder="imap.company.ru"
                  onChange={(value) => updateDraft(draft.id, { imapHost: value })}
                />
                <TextInput
                  label="Login"
                  value={draft.username}
                  placeholder="обычно полный email"
                  onChange={(value) => updateDraft(draft.id, { username: value })}
                />
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-[120px_150px_1fr_1fr]">
                <TextInput
                  label="Port"
                  type="number"
                  value={String(draft.imapPort)}
                  onChange={(value) => updateDraft(draft.id, { imapPort: Number(value || 993) })}
                />
                <label className="flex items-end gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    checked={draft.imapSsl}
                    onChange={(event) => updateDraft(draft.id, { imapSsl: event.target.checked })}
                  />
                  SSL
                </label>
                <TextInput
                  label="App password"
                  type="password"
                  value={draft.appPassword}
                  placeholder="пароль приложения"
                  onChange={(value) => updateDraft(draft.id, { appPassword: value })}
                />
                <TextInput
                  label="Папки через запятую"
                  value={draft.folders}
                  placeholder="INBOX, Sent"
                  onChange={(value) => updateDraft(draft.id, { folders: value })}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button type="button" variant="secondary" onClick={addMailbox}>
            <Plus className="mr-2 h-4 w-4" />
            Добавить почту
          </Button>
          <Button type="button" onClick={saveMailboxes} loading={saving} disabled={!canUseApi || saving}>
            <KeyRound className="mr-2 h-4 w-4" />
            Подключить и проверить
          </Button>
          <span className="text-xs text-muted-foreground">
            Готово к отправке: {filledDrafts.length}. Пароль очистится из формы после сохранения.
          </span>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="card p-5">
          <div className="flex items-center gap-2">
            <Inbox className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Глубина импорта</h2>
          </div>
          <div className="mt-4 space-y-2">
            {(Object.keys(scopeLabels) as ScopeKey[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setSyncScope(key)}
                className={cn(
                  'w-full rounded-lg border px-3 py-2 text-left text-sm transition hover:border-primary hover:bg-primary/5',
                  syncScope === key ? 'border-primary bg-primary/10 text-foreground' : 'border-border text-muted-foreground',
                )}
              >
                {scopeLabels[key]}
              </button>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-lg font-semibold">Период выгрузки</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Настройка применяется к новым подключениям. Уже подключённый ящик можно выгрузить повторно из списка ниже.
          </p>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {(Object.keys(periodLabels) as PeriodKey[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setPeriod(key)}
                className={cn(
                  'rounded-lg border px-3 py-2 text-sm font-medium transition hover:border-primary hover:bg-primary/5',
                  period === key ? 'border-primary bg-primary text-white' : 'border-border bg-white text-foreground',
                )}
              >
                {periodLabels[key]}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Подключённые почты</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Каждый ящик можно проверить и запустить на выгрузку отдельно.
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={loadConnections} disabled={!canUseApi || loading}>
            <RefreshCw className={cn('mr-2 h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
        </div>

        <div className="mt-5 grid gap-3">
          {loading ? (
            <div className="rounded-xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Загружаем подключения...
            </div>
          ) : connections.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-muted/30 p-5 text-sm text-muted-foreground">
              Почтовые ящики ещё не подключены.
            </div>
          ) : (
            connections.map((connection) => (
              <div
                key={connection.id}
                className="grid gap-4 rounded-xl border border-border bg-white p-4 shadow-sm xl:grid-cols-[1fr_auto]"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-base font-semibold text-foreground">{connection.email_address}</div>
                    <Badge tone={connection.status === 'active' ? 'success' : connection.status === 'error' ? 'danger' : 'neutral'}>
                      {statusLabels[connection.status]}
                    </Badge>
                    <Badge tone="neutral">{providerDefaults[connection.provider]?.label ?? connection.provider}</Badge>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                    <Metric label="IMAP" value={`${connection.imap_host}:${connection.imap_port}`} />
                    <Metric label="Папки" value={connection.folders.join(', ') || 'INBOX'} />
                    <Metric label="Период" value={periodLabels[connection.period]} />
                    <Metric label="Последняя выгрузка" value={formatDate(connection.last_sync_at)} />
                    <Metric label="Импортировано" value={String(connection.last_counts?.messages_imported ?? 0)} />
                    <Metric label="Пропущено" value={String(connection.last_counts?.messages_skipped ?? 0)} />
                    <Metric label="Ошибок" value={String(connection.last_counts?.messages_failed ?? 0)} />
                    <Metric label="Режим" value={scopeLabels[connection.sync_scope]} />
                  </div>
                  {connection.last_error ? (
                    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                      {connection.last_error}
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-start gap-2 xl:justify-end">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => testConnection(connection.id)}
                    loading={busyId === connection.id}
                  >
                    Проверить
                  </Button>
                  <Button
                    type="button"
                    onClick={() => startExport(connection)}
                    loading={busyId === connection.id}
                    disabled={connection.status === 'paused'}
                  >
                    <PlayCircle className="mr-2 h-4 w-4" />
                    Выгрузить
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
      />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 break-words font-medium text-foreground">{value}</div>
    </div>
  );
}

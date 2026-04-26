'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  Building2,
  CreditCard,
  Coins,
  ContactRound,
  DatabaseZap,
  DownloadCloud,
  FileText,
  FileAudio,
  LineChart,
  LockKeyhole,
  Plus,
  ReceiptText,
  Search,
  WalletCards,
} from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { isCustomerVisibleCrmConnection } from '@/lib/connectionVisibility';
import type { CrmConnection, DadataPartySuggestion, PaymentCreateResponse, TokenAccount, TokenLedgerEntry } from '@/lib/types';
import { getTopUpPacks } from '@/lib/pricing';
import { formatDate, formatNumber, toIntlLocale } from '@/lib/utils';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

export default function BalancePage() {
  const t = useTranslations('cabinet.balancePage');
  const tConnections = useTranslations('cabinet.connections');
  const locale = useLocale();
  const { user } = useUserAuth();
  const { toast } = useToast();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const [account, setAccount] = useState<TokenAccount | null>(null);
  const [ledger, setLedger] = useState<TokenLedgerEntry[]>([]);
  const [connections, setConnections] = useState<CrmConnection[]>([]);
  const [loading, setLoading] = useState(Boolean(wsId));
  const [selectedPackKey, setSelectedPackKey] = useState<string | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<'card' | 'invoice'>('card');
  const [innQuery, setInnQuery] = useState('');
  const [partySuggestions, setPartySuggestions] = useState<DadataPartySuggestion[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<DadataPartySuggestion | null>(null);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [paymentResult, setPaymentResult] = useState<PaymentCreateResponse | null>(null);
  const topUpPacks = getTopUpPacks(locale);
  const selectedPack = topUpPacks.find((pack) => pack.key === selectedPackKey) ?? null;

  useEffect(() => {
    if (!wsId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get<TokenAccount>(`/workspaces/${wsId}/billing/token-account`),
      api.get<{ items: TokenLedgerEntry[] }>(`/workspaces/${wsId}/billing/token-ledger`),
      api.get<CrmConnection[]>(`/workspaces/${wsId}/crm/connections`),
    ])
      .then(([tokenAccount, tokenLedger, crmConnections]) => {
        if (cancelled) return;
        setAccount(tokenAccount);
        setLedger(tokenLedger.items ?? []);
        setConnections((crmConnections ?? []).filter(isCustomerVisibleCrmConnection));
      })
      .catch(() => {
        if (cancelled) return;
        setAccount(null);
        setLedger([]);
        setConnections([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [wsId]);

  if (!wsId) {
    return <EmptyState title={tConnections('noWorkspaceTitle')} description={tConnections('noWorkspaceBody')} />;
  }

  const showPaymentError = (err: unknown, fallback: string) => {
    const message = err instanceof ApiError ? err.message : fallback;
    toast({ kind: 'error', title: 'Оплата CODE9', description: message });
  };

  const refreshBilling = async () => {
    if (!wsId) return;
    const [tokenAccount, tokenLedger] = await Promise.all([
      api.get<TokenAccount>(`/workspaces/${wsId}/billing/token-account`),
      api.get<{ items: TokenLedgerEntry[] }>(`/workspaces/${wsId}/billing/token-ledger`),
    ]);
    setAccount(tokenAccount);
    setLedger(tokenLedger.items ?? []);
  };

  const suggestCompany = async () => {
    if (!wsId || innQuery.trim().length < 3) return;
    setSuggestLoading(true);
    setSelectedCompany(null);
    try {
      const data = await api.post<{ items: DadataPartySuggestion[] }>(`/workspaces/${wsId}/billing/dadata/party-suggest`, {
        query: innQuery.trim(),
        count: 5,
      });
      setPartySuggestions(data.items ?? []);
    } catch (err) {
      setPartySuggestions([]);
      showPaymentError(err, 'Не удалось найти компанию по ИНН');
    } finally {
      setSuggestLoading(false);
    }
  };

  const createCardPayment = async () => {
    if (!wsId || !selectedPack) return;
    setPaymentLoading(true);
    setPaymentResult(null);
    try {
      const data = await api.post<PaymentCreateResponse>(`/workspaces/${wsId}/billing/payments/card`, {
        purchase_type: 'token_topup',
        token_pack_key: selectedPack.key,
      });
      setPaymentResult(data);
      if (data.payment_url) {
        window.location.assign(data.payment_url);
        return;
      }
      toast({ kind: 'success', title: 'Платёж создан', description: 'Ссылка на оплату сформирована.' });
    } catch (err) {
      showPaymentError(err, 'Не удалось создать оплату картой');
    } finally {
      setPaymentLoading(false);
    }
  };

  const createInvoicePayment = async () => {
    if (!wsId || !selectedPack || !selectedCompany) return;
    setPaymentLoading(true);
    setPaymentResult(null);
    try {
      const data = await api.post<PaymentCreateResponse>(`/workspaces/${wsId}/billing/payments/invoice`, {
        purchase_type: 'token_topup',
        token_pack_key: selectedPack.key,
        payer: selectedCompany,
      });
      setPaymentResult(data);
      toast({ kind: 'success', title: 'Счёт создан', description: data.message ?? data.order.invoice_number ?? undefined });
      await refreshBilling();
    } catch (err) {
      showPaymentError(err, 'Не удалось сформировать счёт');
    } finally {
      setPaymentLoading(false);
    }
  };
  const todayLedger = ledger.filter(isTodayEntry);
  const todayDebits = todayLedger.filter((entry) => entry.amount_tokens < 0);
  const exportSpend = sumAbsTokens(todayDebits.filter((entry) => entryMatches(entry, ['export', 'выгруз'])));
  const transcriptionSpend = sumAbsTokens(todayDebits.filter((entry) => entryMatches(entry, ['transcrib', 'транскриб', 'call', 'звон'])));
  const aiSpend = sumAbsTokens(todayDebits.filter((entry) => entryMatches(entry, ['ai', 'analysis', 'анализ', 'email', 'пись', 'chat'])));
  const totalTodaySpend = sumAbsTokens(todayDebits);
  const otherSpend = Math.max(0, totalTodaySpend - exportSpend - transcriptionSpend - aiSpend);
  const importCounts = aggregateConnectionCounts(connections);
  const todayImportCounts = aggregateTodayConnectionCounts(connections);

  return (
    <div className="space-y-6">
      <header className="cabinet-page-hero flex items-start justify-between gap-4 flex-wrap p-5">
        <div>
          <h1 className="text-2xl font-semibold">{t('title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
        </div>
        <Badge tone="neutral">{t('safeMode')}</Badge>
      </header>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-52" />
        </div>
      ) : (
        <>
          <section className="grid gap-3 md:grid-cols-4">
            <MetricCard icon={<WalletCards className="h-5 w-5" />} label={t('total')} value={account ? formatNumber(account.balance_tokens, locale) : '0'} />
            <MetricCard icon={<Coins className="h-5 w-5" />} label={t('available')} value={account ? formatNumber(account.available_tokens, locale) : '0'} />
            <MetricCard icon={<LockKeyhole className="h-5 w-5" />} label={t('reserved')} value={account ? formatNumber(account.reserved_tokens, locale) : '0'} />
            <MetricCard icon={<Plus className="h-5 w-5" />} label={t('included')} value={account ? `${formatNumber(account.included_monthly_tokens, locale)} ${perMonth(locale)}` : '0'} />
          </section>

          <section className="cabinet-page-hero p-5 space-y-4">
            <div>
              <h2 className="text-lg font-semibold">{t('spendDashboardTitle')}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{t('spendDashboardBody')}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard icon={<DownloadCloud className="h-5 w-5" />} label={t('exportSpendToday')} value={formatNumber(exportSpend, locale)} />
              <MetricCard icon={<FileAudio className="h-5 w-5" />} label={t('transcriptionSpendToday')} value={formatNumber(transcriptionSpend, locale)} />
              <MetricCard icon={<LineChart className="h-5 w-5" />} label={t('aiSpendToday')} value={formatNumber(aiSpend, locale)} />
              <MetricCard icon={<ReceiptText className="h-5 w-5" />} label={t('otherSpendToday')} value={formatNumber(otherSpend, locale)} />
            </div>
          </section>

          <section className="cabinet-page-hero p-5 space-y-4">
            <div>
              <h2 className="text-lg font-semibold">{t('importDashboardTitle')}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{t('importDashboardBody')}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
              <MetricCard icon={<DatabaseZap className="h-5 w-5" />} label={t('pipelinesImported')} value={formatNumber(importCounts.pipelines, locale)} />
              <MetricCard icon={<Building2 className="h-5 w-5" />} label={t('companiesImported')} value={formatNumber(importCounts.companies, locale)} />
              <MetricCard icon={<ContactRound className="h-5 w-5" />} label={t('contactsImported')} value={formatNumber(importCounts.contacts, locale)} />
              <MetricCard icon={<DownloadCloud className="h-5 w-5" />} label={t('dealsImported')} value={formatNumber(importCounts.deals, locale)} />
              <MetricCard icon={<Plus className="h-5 w-5" />} label={t('newDealsToday')} value={`≈ ${formatNumber(todayImportCounts.deals, locale)}`} />
              <MetricCard icon={<Plus className="h-5 w-5" />} label={t('newContactsToday')} value={`≈ ${formatNumber(todayImportCounts.contacts, locale)}`} />
            </div>
          </section>

          <section className="cabinet-page-hero p-5 space-y-4">
            <div>
              <h2 className="text-lg font-semibold">{t('topUpsTitle')}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{t('topUpsBody')}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {topUpPacks.map((pack) => (
                <article key={pack.key} className="cabinet-pricing-card rounded-md p-4">
                  <div className="font-semibold">{pack.name}</div>
                  <div className="mt-2 text-2xl font-semibold">{formatRub(pack.prices.monthly, locale)}</div>
                  <p className="mt-2 text-xs text-muted-foreground">{pack.scope}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {pack.tags.map((tag) => (
                      <Badge key={tag} tone="neutral">{tag}</Badge>
                    ))}
                  </div>
                  <Button
                    type="button"
                    className="mt-4 w-full"
                    variant={selectedPackKey === pack.key ? 'primary' : 'secondary'}
                    onClick={() => {
                      setSelectedPackKey(pack.key);
                      setPaymentResult(null);
                    }}
                  >
                    {selectedPackKey === pack.key ? 'Выбрано' : 'Пополнить'}
                  </Button>
                </article>
              ))}
            </div>
            {selectedPack ? (
              <div className="rounded-xl border border-primary/20 bg-white/85 p-4 shadow-soft">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <h3 className="font-semibold">Оплата пакета: {selectedPack.name}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Выберите оплату картой через Т-Банк или сформируйте счёт на юрлицо через поиск по ИНН.
                    </p>
                  </div>
                  <div className="flex rounded-lg border border-border bg-muted p-1">
                    <button
                      type="button"
                      className={`rounded-md px-3 py-1.5 text-sm font-medium ${paymentMethod === 'card' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground'}`}
                      onClick={() => setPaymentMethod('card')}
                    >
                      <CreditCard className="mr-1 inline h-4 w-4" />
                      Картой
                    </button>
                    <button
                      type="button"
                      className={`rounded-md px-3 py-1.5 text-sm font-medium ${paymentMethod === 'invoice' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground'}`}
                      onClick={() => setPaymentMethod('invoice')}
                    >
                      <FileText className="mr-1 inline h-4 w-4" />
                      Счёт
                    </button>
                  </div>
                </div>

                {paymentMethod === 'card' ? (
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <Button type="button" onClick={createCardPayment} loading={paymentLoading}>
                      Перейти к оплате
                    </Button>
                    <p className="text-sm text-muted-foreground">
                      После успешного webhook платёж автоматически пополнит баланс AIC9 токенов.
                    </p>
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        className="block w-full rounded-md border border-border bg-white px-3 py-2 text-sm"
                        value={innQuery}
                        onChange={(event) => setInnQuery(event.target.value)}
                        placeholder="Введите ИНН или название компании"
                      />
                      <Button type="button" variant="secondary" onClick={suggestCompany} loading={suggestLoading}>
                        <Search className="h-4 w-4" />
                        Найти
                      </Button>
                    </div>
                    {partySuggestions.length > 0 ? (
                      <div className="grid gap-2">
                        {partySuggestions.map((item) => (
                          <button
                            key={`${item.inn}-${item.kpp ?? ''}-${item.ogrn ?? ''}`}
                            type="button"
                            className={`rounded-lg border p-3 text-left text-sm transition ${selectedCompany?.inn === item.inn && selectedCompany?.kpp === item.kpp ? 'border-primary bg-primary/10' : 'border-border bg-white hover:border-primary'}`}
                            onClick={() => setSelectedCompany(item)}
                          >
                            <div className="font-semibold">{item.name ?? item.value}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              ИНН {item.inn}{item.kpp ? ` · КПП ${item.kpp}` : ''}{item.address ? ` · ${item.address}` : ''}
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <Button type="button" onClick={createInvoicePayment} loading={paymentLoading} disabled={!selectedCompany}>
                      Сформировать счёт
                    </Button>
                  </div>
                )}

                {paymentResult ? (
                  <div className="mt-4 rounded-lg border border-border bg-muted/40 p-3 text-sm">
                    <div className="font-medium">Заказ {paymentResult.order.invoice_number ?? paymentResult.order.id}</div>
                    <div className="text-muted-foreground">
                      Статус: {paymentResult.order.status} · сумма: {formatRub(paymentResult.order.amount_cents / 100, locale)}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>

          <section className="cabinet-page-hero overflow-hidden">
            <div className="p-5 border-b border-border font-semibold">{t('history')}</div>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground bg-muted">
                <tr>
                  <th className="px-5 py-2">{t('date')}</th>
                  <th className="px-5 py-2">{t('description')}</th>
                  <th className="px-5 py-2 text-right">{t('tokens')}</th>
                  <th className="px-5 py-2 text-right">{t('balanceAfter')}</th>
                </tr>
              </thead>
              <tbody>
                {ledger.length === 0 && (
                  <tr>
                    <td className="px-5 py-4 text-muted-foreground" colSpan={4}>
                      {t('emptyHistory')}
                    </td>
                  </tr>
                )}
                {ledger.map((entry) => (
                  <tr key={entry.id} className="border-t border-border">
                    <td className="px-5 py-2">{formatDate(entry.created_at, locale)}</td>
                    <td className="px-5 py-2">
                      <div>{entry.description}</div>
                      {entry.reference && <div className="mt-1 text-xs text-muted-foreground">{entry.reference}</div>}
                    </td>
                    <td className={`px-5 py-2 text-right font-medium ${entry.amount_tokens < 0 ? 'text-danger' : 'text-success'}`}>
                      {entry.amount_tokens > 0 ? '+' : ''}
                      {formatNumber(entry.amount_tokens, locale)}
                    </td>
                    <td className="px-5 py-2 text-right font-medium">
                      {formatNumber(entry.balance_after_tokens, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="cabinet-metric-card p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="text-primary">{icon}</span>
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function isTodayEntry(entry: TokenLedgerEntry): boolean {
  if (!entry.created_at) return false;
  const createdAt = new Date(entry.created_at);
  if (Number.isNaN(createdAt.getTime())) return false;
  const now = new Date();
  return (
    createdAt.getFullYear() === now.getFullYear() &&
    createdAt.getMonth() === now.getMonth() &&
    createdAt.getDate() === now.getDate()
  );
}

function entryMatches(entry: TokenLedgerEntry, needles: string[]): boolean {
  const haystack = [entry.kind, entry.description, entry.reference]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return needles.some((needle) => haystack.includes(needle));
}

function sumAbsTokens(entries: TokenLedgerEntry[]): number {
  return entries.reduce((sum, entry) => sum + Math.abs(entry.amount_tokens), 0);
}

function aggregateConnectionCounts(connections: CrmConnection[]) {
  return connections.reduce(
    (acc, connection) => {
      const counts =
        connection.metadata?.active_export?.counts ??
        connection.metadata?.last_pull_counts ??
        connection.metadata?.last_trial_export_counts ??
        {};
      acc.pipelines += counts.pipelines ?? 0;
      acc.companies += counts.companies ?? 0;
      acc.contacts += counts.contacts ?? 0;
      acc.deals += counts.deals ?? 0;
      return acc;
    },
    { pipelines: 0, companies: 0, contacts: 0, deals: 0 },
  );
}

function aggregateTodayConnectionCounts(connections: CrmConnection[]) {
  return aggregateConnectionCounts(
    connections.filter((connection) => isTodayIso(connection.metadata?.last_pull_at ?? connection.metadata?.active_export?.completed_at ?? null)),
  );
}

function isTodayIso(value: string | null | undefined): boolean {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function formatRub(value: number, locale: string): string {
  return new Intl.NumberFormat(toIntlLocale(locale), {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value);
}

function perMonth(locale: string): string {
  if (locale === 'en') return '/ mo';
  if (locale === 'es') return '/ mes';
  return '/ мес';
}

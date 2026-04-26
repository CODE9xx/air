'use client';

import { useTranslations, useLocale } from 'next-intl';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type {
  BillingAccount,
  BillingLedgerEntry,
  TokenAccount,
  TokenLedgerEntry,
} from '@/lib/types';
import {
  getAiTokenRates,
  getBillingPeriods,
  getLaunchServices,
  getPricingPlans,
  getTopUpPacks,
  type PricingPeriodKey,
} from '@/lib/pricing';
import { cn, formatDate, formatMoney, formatNumber, toIntlLocale } from '@/lib/utils';
import { Skeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { useToast } from '@/components/ui/Toast';

export function BillingPanel({ workspaceId }: { workspaceId: string }) {
  const t = useTranslations('cabinet.billing');
  const locale = useLocale();
  const { toast } = useToast();
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [ledger, setLedger] = useState<BillingLedgerEntry[]>([]);
  const [tokenAccount, setTokenAccount] = useState<TokenAccount | null>(null);
  const [tokenLedger, setTokenLedger] = useState<TokenLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<PricingPeriodKey>('monthly');
  const billingPeriods = getBillingPeriods(locale);
  const pricingPlans = getPricingPlans(locale);
  const aiTokenRates = getAiTokenRates(locale);
  const topUpPacks = getTopUpPacks(locale);
  const launchServices = getLaunchServices(locale);
  const bt = (key: BillingTextKey) => billingText(locale, key);

  useEffect(() => {
    (async () => {
      try {
        const [a, l, tokenAccountResponse, tokenLedgerResponse] = await Promise.all([
          api.get<BillingAccount>(`/workspaces/${workspaceId}/billing/account`),
          api.get<{ items: BillingLedgerEntry[] }>(`/workspaces/${workspaceId}/billing/ledger`),
          api.get<TokenAccount>(`/workspaces/${workspaceId}/billing/token-account`),
          api.get<{ items: TokenLedgerEntry[] }>(`/workspaces/${workspaceId}/billing/token-ledger`),
        ]);
        setAccount(a);
        setLedger(l.items ?? []);
        setTokenAccount(tokenAccountResponse);
        setTokenLedger(tokenLedgerResponse.items ?? []);
      } finally {
        setLoading(false);
      }
    })();
  }, [workspaceId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (!account) return null;

  const currentPlanKey = matchPlanKey(tokenAccount?.plan_key ?? account.plan);
  const currentPlan = pricingPlans.find((plan) => plan.key === currentPlanKey) ?? null;
  const currentPlanName = getPlanDisplayName(tokenAccount?.plan_key ?? account.plan, locale, bt('planNotSelected'));

  return (
    <div className="space-y-6">
      <div className="card p-6 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-muted-foreground">{t('balance')}</div>
          <div className="mt-1 text-3xl font-semibold">{formatMoney(account.balance_cents, account.currency, locale)}</div>
          <div className="mt-2 text-xs text-muted-foreground">{t('plan')}: {currentPlanName}</div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <SummaryPill
            label={bt('planTokens')}
            value={
              tokenAccount
                ? `${formatNumber(tokenAccount.included_monthly_tokens, locale)} ${perMonth(locale)}`
                : currentPlan
                  ? `${formatNumber(currentPlan.tokens, locale)} ${perMonth(locale)}`
                  : bt('planNotSelected')
            }
          />
          <SummaryPill
            label={bt('availableTokens')}
            value={tokenAccount ? formatNumber(tokenAccount.available_tokens, locale) : '—'}
          />
          <SummaryPill
            label={bt('reservedTokens')}
            value={tokenAccount ? formatNumber(tokenAccount.reserved_tokens, locale) : '—'}
          />
          <SummaryPill label={bt('databaseUpdate')} value={currentPlan?.updateInterval ?? bt('dependsOnPlan')} />
        </div>
        <Button onClick={() => toast({ kind: 'info', title: t('topUp') })}>{t('topUp')}</Button>
      </div>

      <section className="card p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">{bt('tokenBalanceTitle')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {bt('tokenBalanceBody')}
            </p>
          </div>
          <Badge tone={tokenAccount && tokenAccount.available_tokens > 0 ? 'success' : 'warning'}>
            {tokenAccount ? `${formatNumber(tokenAccount.available_tokens, locale)} ${bt('availableShort')}` : bt('noBalance')}
          </Badge>
        </div>
        <div className="grid gap-3 md:grid-cols-4 text-sm">
          <SummaryPill
            label={bt('totalBalance')}
            value={tokenAccount ? formatNumber(tokenAccount.balance_tokens, locale) : '0'}
          />
          <SummaryPill
            label={bt('available')}
            value={tokenAccount ? formatNumber(tokenAccount.available_tokens, locale) : '0'}
          />
          <SummaryPill
            label={bt('reserved')}
            value={tokenAccount ? formatNumber(tokenAccount.reserved_tokens, locale) : '0'}
          />
          <SummaryPill
            label={bt('plan')}
            value={tokenAccount?.plan_key ?? account.plan}
          />
        </div>
      </section>

      <section className="card p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
                <h2 className="text-lg font-semibold">{bt('plansTitle')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {bt('plansBody')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {billingPeriods.map((item) => (
              <Button
                key={item.key}
                type="button"
                size="sm"
                variant={period === item.key ? 'primary' : 'secondary'}
                onClick={() => setPeriod(item.key)}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
          {pricingPlans.map((plan) => (
            <PlanCard
              key={plan.key}
              plan={plan}
              period={period}
              periodLabel={plan.customPeriodLabel ?? formatPlanPeriodLabel(period, plan.prices[period], locale, billingPeriods)}
              locale={locale}
              isCurrent={plan.key === currentPlanKey}
            />
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
        <div className="card p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">{bt('tokenUsageTitle')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {bt('tokenUsageBody')}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {aiTokenRates.map((rate) => (
              <div key={rate.title} className="rounded-md border border-border p-3">
                <div className="text-2xl font-semibold tabular-nums">{rate.value}</div>
                <div className="mt-1 font-medium">{rate.title}</div>
                <p className="mt-1 text-xs text-muted-foreground">{rate.body}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">{bt('topUpsTitle')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {bt('topUpsBody')}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {topUpPacks.map((pack) => (
              <div key={pack.key} className="rounded-md border border-border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium">{pack.name}</div>
                  <div className="font-semibold whitespace-nowrap">{formatRub(pack.prices[period], locale)}</div>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{pack.scope}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {pack.tags.map((tag) => (
                    <Badge key={tag} tone="neutral">{tag}</Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="card p-5 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">{bt('launchTitle')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {bt('launchBody')}
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {launchServices.map((service) => (
            <div key={service.name} className="rounded-md border border-border p-3">
              <div className="font-medium">{service.name}</div>
              <div className="mt-2 text-xl font-semibold">{service.price}</div>
              <p className="mt-2 text-xs text-muted-foreground">{service.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="card">
        <div className="p-5 border-b border-border font-semibold">{t('history')}</div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground bg-muted">
            <tr>
              <th className="px-5 py-2">{t('date')}</th>
              <th className="px-5 py-2">{t('description')}</th>
              <th className="px-5 py-2 text-right">{t('amount')}</th>
            </tr>
          </thead>
          <tbody>
            {ledger.map((e) => (
              <tr key={e.id} className="border-t border-border">
                <td className="px-5 py-2">{formatDate(e.created_at, locale)}</td>
                <td className="px-5 py-2">{e.description}</td>
                <td className={`px-5 py-2 text-right font-medium ${e.amount_cents < 0 ? 'text-danger' : 'text-success'}`}>
                  {formatMoney(e.amount_cents, e.currency, locale)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="p-5 border-b border-border font-semibold">{bt('tokenHistory')}</div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground bg-muted">
            <tr>
              <th className="px-5 py-2">{t('date')}</th>
              <th className="px-5 py-2">{t('description')}</th>
              <th className="px-5 py-2 text-right">{bt('tokens')}</th>
              <th className="px-5 py-2 text-right">{bt('balanceAfter')}</th>
            </tr>
          </thead>
          <tbody>
            {tokenLedger.length === 0 && (
              <tr>
                <td className="px-5 py-4 text-muted-foreground" colSpan={4}>
                  {bt('emptyTokenHistory')}
                </td>
              </tr>
            )}
            {tokenLedger.map((entry) => (
              <tr key={entry.id} className="border-t border-border">
                <td className="px-5 py-2">{formatDate(entry.created_at, locale)}</td>
                <td className="px-5 py-2">
                  <div>{entry.description}</div>
                  {entry.reference && (
                    <div className="mt-1 text-xs text-muted-foreground">{entry.reference}</div>
                  )}
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
      </div>
    </div>
  );
}

type Plan = ReturnType<typeof getPricingPlans>[number];

function PlanCard({
  plan,
  period,
  periodLabel,
  locale,
  isCurrent,
}: {
  plan: Plan;
  period: PricingPeriodKey;
  periodLabel: string;
  locale: string;
  isCurrent: boolean;
}) {
  const price = plan.prices[period];

  return (
    <article
      className={cn(
        'rounded-lg border border-border bg-white p-4 shadow-soft',
        plan.popular && 'border-primary/40',
        isCurrent && 'ring-2 ring-primary/30',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{plan.name}</h3>
            {plan.popular && <Badge tone="info">{billingText(locale, 'popular')}</Badge>}
          </div>
          <div className="mt-2">
            <Badge tone="neutral">{plan.badge}</Badge>
          </div>
        </div>
        {isCurrent && <Badge tone="success">{billingText(locale, 'current')}</Badge>}
      </div>
      <div className="mt-4">
        <div className="text-3xl font-semibold tabular-nums">{plan.customPriceLabel ?? formatRub(price, locale)}</div>
        <div className="mt-1 text-xs text-muted-foreground">{periodLabel}</div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{plan.summary}</p>
      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <SummaryPill label={billingText(locale, 'tokens')} value={`${formatNumber(plan.tokens, locale)} ${perMonth(locale)}`} />
        <SummaryPill label={billingText(locale, 'aiUsers')} value={`${upTo(locale)} ${plan.users}`} />
        <SummaryPill label={billingText(locale, 'updates')} value={plan.updateInterval} />
        <SummaryPill label={billingText(locale, 'calls')} value={`${upTo(locale)} ${formatNumber(plan.callMinutes, locale)} ${minutesPerMonth(locale)}`} />
      </div>
      <ul className="mt-4 space-y-2 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex gap-2">
            <span className="text-success">✓</span>
            <span>{feature}</span>
          </li>
        ))}
        {plan.excluded.map((feature) => (
          <li key={feature} className="flex gap-2 text-muted-foreground">
            <span>—</span>
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-2">
        <Badge tone="neutral">{billingText(locale, 'rollover')}: {plan.rollover}</Badge>
        <Badge tone="neutral">{billingText(locale, 'topup')}: {plan.topup}</Badge>
      </div>
    </article>
  );
}

function SummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

function formatPlanPeriodLabel(
  period: PricingPeriodKey,
  price: number,
  locale: string,
  periods: ReturnType<typeof getBillingPeriods>,
): string {
  if (period === 'monthly') {
    if (locale === 'en') return '/ month';
    if (locale === 'es') return '/ mes';
    return '/ месяц';
  }
  const months = period === 'six' ? 6 : 12;
  const suffix = periods.find((item) => item.key === period)?.suffix;
  if (locale === 'en') return `${suffix} · ≈ ${formatRub(price / months, locale)}/mo`;
  if (locale === 'es') return `${suffix} · ≈ ${formatRub(price / months, locale)}/mes`;
  return `${suffix} · ≈ ${formatRub(price / months, locale)}/мес`;
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

function upTo(locale: string): string {
  if (locale === 'en') return 'up to';
  if (locale === 'es') return 'hasta';
  return 'до';
}

function minutesPerMonth(locale: string): string {
  if (locale === 'en') return 'min/mo';
  if (locale === 'es') return 'min/mes';
  return 'мин/мес';
}

const billingTextMap = {
  ru: {
    planTokens: 'AI-токены тарифа',
    planNotSelected: 'тариф не выбран',
    availableTokens: 'Доступно токенов',
    reservedTokens: 'Зарезервировано',
    databaseUpdate: 'Обновление базы',
    dependsOnPlan: 'зависит от тарифа',
    tokenBalanceTitle: 'Баланс AIC9-токенов',
    tokenBalanceBody: 'Перед реальной выгрузкой токены резервируются. После успешной выгрузки резерв списывается, при ошибке возвращается.',
    availableShort: 'доступно',
    noBalance: 'нет баланса',
    totalBalance: 'Всего на балансе',
    available: 'Доступно',
    reserved: 'В резерве',
    plan: 'План',
    plansTitle: 'Тарифы и AI-токены',
    plansBody: 'Подписка оплачивает платформу, включённые токены расходуются на AI-действия. Реальные платежи здесь пока не запускаются.',
    tokenUsageTitle: 'Как расходуются токены',
    tokenUsageBody: 'Это внутренние AIC9-токены тарифа, не технические OpenAI-токены из оценки полной базы.',
    topUpsTitle: 'Докупка токенов',
    topUpsBody: 'На Старт доступен Call Pack, на Команда, Про и Enterprise — Universal Pack.',
    launchTitle: 'Запуск, внедрение и аудит',
    launchBody: 'Эти услуги оплачиваются отдельно или используются как бонус при долгой оплате.',
    tokenHistory: 'История токенов',
    tokens: 'Токены',
    balanceAfter: 'Баланс после',
    emptyTokenHistory: 'Списаний токенов пока нет.',
    popular: 'Популярный',
    current: 'Текущий',
    aiUsers: 'AI-пользователи',
    updates: 'Обновление',
    calls: 'Звонки',
    rollover: 'Перенос',
    topup: 'Докупка',
  },
  en: {
    planTokens: 'Plan AI tokens',
    planNotSelected: 'plan not selected',
    availableTokens: 'Available tokens',
    reservedTokens: 'Reserved',
    databaseUpdate: 'Database update',
    dependsOnPlan: 'depends on plan',
    tokenBalanceTitle: 'AIC9 token balance',
    tokenBalanceBody: 'Before a real export, tokens are reserved. After a successful export the reserve is charged; on error it is returned.',
    availableShort: 'available',
    noBalance: 'no balance',
    totalBalance: 'Total balance',
    available: 'Available',
    reserved: 'Reserved',
    plan: 'Plan',
    plansTitle: 'Plans and AI tokens',
    plansBody: 'Subscription pays for the platform; included tokens are spent on AI actions. Real payments are not active here yet.',
    tokenUsageTitle: 'How tokens are spent',
    tokenUsageBody: 'These are internal AIC9 plan tokens, not technical OpenAI tokens from the full database estimate.',
    topUpsTitle: 'Token top-ups',
    topUpsBody: 'Start has Call Pack; Team, Pro and Enterprise have Universal Pack.',
    launchTitle: 'Launch, implementation and audit',
    launchBody: 'These services are paid separately or used as a bonus for long-term payment.',
    tokenHistory: 'Token history',
    tokens: 'Tokens',
    balanceAfter: 'Balance after',
    emptyTokenHistory: 'No token charges yet.',
    popular: 'Popular',
    current: 'Current',
    aiUsers: 'AI users',
    updates: 'Update',
    calls: 'Calls',
    rollover: 'Rollover',
    topup: 'Top-up',
  },
  es: {
    planTokens: 'Tokens IA del plan',
    planNotSelected: 'plan no seleccionado',
    availableTokens: 'Tokens disponibles',
    reservedTokens: 'Reservado',
    databaseUpdate: 'Actualización de base',
    dependsOnPlan: 'depende del plan',
    tokenBalanceTitle: 'Balance de tokens AIC9',
    tokenBalanceBody: 'Antes de una exportación real, los tokens se reservan. Tras una exportación correcta se cargan; si hay error, se devuelven.',
    availableShort: 'disponibles',
    noBalance: 'sin balance',
    totalBalance: 'Balance total',
    available: 'Disponible',
    reserved: 'Reservado',
    plan: 'Plan',
    plansTitle: 'Planes y tokens IA',
    plansBody: 'La suscripción paga la plataforma; los tokens incluidos se gastan en acciones IA. Los pagos reales aún no están activos aquí.',
    tokenUsageTitle: 'Cómo se gastan los tokens',
    tokenUsageBody: 'Son tokens internos AIC9 del plan, no tokens técnicos de OpenAI de la estimación de base completa.',
    topUpsTitle: 'Recarga de tokens',
    topUpsBody: 'Inicio tiene Call Pack; Equipo, Pro y Enterprise tienen Universal Pack.',
    launchTitle: 'Lanzamiento, implementación y auditoría',
    launchBody: 'Estos servicios se pagan por separado o se usan como bonus en pagos de largo plazo.',
    tokenHistory: 'Historial de tokens',
    tokens: 'Tokens',
    balanceAfter: 'Balance después',
    emptyTokenHistory: 'Aún no hay cargos de tokens.',
    popular: 'Popular',
    current: 'Actual',
    aiUsers: 'Usuarios IA',
    updates: 'Actualización',
    calls: 'Llamadas',
    rollover: 'Transferencia',
    topup: 'Recarga',
  },
} as const;

type BillingTextKey = keyof typeof billingTextMap.ru;

function billingText(locale: string, key: BillingTextKey): string {
  if (locale === 'en') return billingTextMap.en[key];
  if (locale === 'es') return billingTextMap.es[key];
  return billingTextMap.ru[key];
}

function matchPlanKey(plan: string): string | null {
  const normalized = plan.toLowerCase();
  return getPricingPlans('ru').find((item) => {
    const name = item.name.toLowerCase();
    return normalized.includes(item.key) || normalized.includes(name);
  })?.key ?? null;
}

function getPlanDisplayName(plan: string, locale: string, fallback: string): string {
  const normalized = plan.toLowerCase();
  if (!normalized || normalized === 'free' || normalized === 'paygo') return fallback;
  return (
    getPricingPlans(locale).find((item) => {
      const name = item.name.toLowerCase();
      return normalized.includes(item.key) || normalized.includes(name);
    })?.name ?? plan
  );
}

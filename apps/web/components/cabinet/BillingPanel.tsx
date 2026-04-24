'use client';

import { useTranslations, useLocale } from 'next-intl';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { BillingAccount, BillingLedgerEntry } from '@/lib/types';
import {
  aiTokenRates,
  billingPeriods,
  launchServices,
  pricingPlans,
  topUpPacks,
  type PricingPeriodKey,
} from '@/lib/pricing';
import { cn, formatDate, formatMoney, formatNumber } from '@/lib/utils';
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
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<PricingPeriodKey>('monthly');

  useEffect(() => {
    (async () => {
      try {
        const [a, l] = await Promise.all([
          api.get<BillingAccount>(`/workspaces/${workspaceId}/billing/account`),
          api.get<{ items: BillingLedgerEntry[] }>(`/workspaces/${workspaceId}/billing/ledger`),
        ]);
        setAccount(a);
        setLedger(l.items ?? []);
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

  const currentPlanKey = matchPlanKey(account.plan);
  const currentPlan = pricingPlans.find((plan) => plan.key === currentPlanKey) ?? null;

  return (
    <div className="space-y-6">
      <div className="card p-6 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-muted-foreground">{t('balance')}</div>
          <div className="mt-1 text-3xl font-semibold">{formatMoney(account.balance_cents, account.currency, locale)}</div>
          <div className="mt-2 text-xs text-muted-foreground">{t('plan')}: {account.plan}</div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <SummaryPill
            label="AI-токены тарифа"
            value={currentPlan ? `${formatNumber(currentPlan.tokens, locale)} / мес` : 'тариф не выбран'}
          />
          <SummaryPill
            label="Обновление базы"
            value={currentPlan?.updateInterval ?? 'зависит от тарифа'}
          />
        </div>
        <Button onClick={() => toast({ kind: 'info', title: t('topUp') })}>{t('topUp')}</Button>
      </div>

      <section className="card p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">Тарифы и AI-токены</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Подписка оплачивает платформу, включённые токены расходуются на AI-действия.
              Реальные платежи здесь пока не запускаются.
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

        <div className="grid gap-3 lg:grid-cols-3">
          {pricingPlans.map((plan) => (
            <PlanCard
              key={plan.key}
              plan={plan}
              period={period}
              locale={locale}
              isCurrent={plan.key === currentPlanKey}
            />
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
        <div className="card p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold">Как расходуются токены</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Это внутренние AIC9-токены тарифа, не технические OpenAI-токены из оценки полной базы.
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
            <h2 className="text-lg font-semibold">Докупка токенов</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              На Старт доступен Call Pack, на Команда и Про — Universal Pack.
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
          <h2 className="text-lg font-semibold">Запуск, внедрение и аудит</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Эти услуги оплачиваются отдельно или используются как бонус при долгой оплате.
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
    </div>
  );
}

type Plan = (typeof pricingPlans)[number];

function PlanCard({
  plan,
  period,
  locale,
  isCurrent,
}: {
  plan: Plan;
  period: PricingPeriodKey;
  locale: string;
  isCurrent: boolean;
}) {
  const price = plan.prices[period];
  const months = period === 'monthly' ? 1 : period === 'six' ? 6 : 12;
  const monthlyEquivalent = price / months;
  const periodLabel = period === 'monthly'
    ? '/ месяц'
    : `${billingPeriods.find((item) => item.key === period)?.suffix} · ≈ ${formatRub(monthlyEquivalent, locale)}/мес`;

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
            {plan.popular && <Badge tone="info">Популярный</Badge>}
          </div>
          <div className="mt-2">
            <Badge tone="neutral">{plan.badge}</Badge>
          </div>
        </div>
        {isCurrent && <Badge tone="success">Текущий</Badge>}
      </div>
      <div className="mt-4">
        <div className="text-3xl font-semibold tabular-nums">{formatRub(price, locale)}</div>
        <div className="mt-1 text-xs text-muted-foreground">{periodLabel}</div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{plan.summary}</p>
      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <SummaryPill label="Токены" value={`${formatNumber(plan.tokens, locale)} / мес`} />
        <SummaryPill label="AI-пользователи" value={`до ${plan.users}`} />
        <SummaryPill label="Обновление" value={plan.updateInterval} />
        <SummaryPill label="Звонки" value={`до ${formatNumber(plan.callMinutes, locale)} мин/мес`} />
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
        <Badge tone="neutral">Перенос: {plan.rollover}</Badge>
        <Badge tone="neutral">Докупка: {plan.topup}</Badge>
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

function formatRub(value: number, locale: string): string {
  return new Intl.NumberFormat(locale === 'ru' ? 'ru-RU' : 'en-US', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value);
}

function matchPlanKey(plan: string): string | null {
  const normalized = plan.toLowerCase();
  return pricingPlans.find((item) => {
    const name = item.name.toLowerCase();
    return normalized.includes(item.key) || normalized.includes(name);
  })?.key ?? null;
}

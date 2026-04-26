'use client';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import {
  Plug,
  Bell,
  Sparkles,
  MessageSquareText,
  Workflow,
  BookOpen,
  Settings,
  SquarePlay,
  CircleHelp,
  BadgeDollarSign,
  LayoutDashboard,
  WalletCards,
} from 'lucide-react';
import { cn, formatNumber, toIntlLocale } from '@/lib/utils';
import { api } from '@/lib/api';
import { isCustomerVisibleCrmConnection } from '@/lib/connectionVisibility';
import { getPricingPlans } from '@/lib/pricing';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { BrandLockup } from '@/components/BrandLockup';
import type { CrmConnection, TokenAccount } from '@/lib/types';

interface Item {
  href: string;
  labelKey: string;
  icon: ReactNode;
}

export function Sidebar() {
  const t = useTranslations('cabinet.sidebar');
  const locale = useLocale();
  const pathname = usePathname() ?? '';
  const { user } = useUserAuth();
  const workspaceId = user?.workspaces?.[0]?.id ?? null;
  const [dashboardBuilderHref, setDashboardBuilderHref] = useState<string | null>(null);
  const [tokenAccount, setTokenAccount] = useState<TokenAccount | null>(null);
  const [tokenBalanceLoading, setTokenBalanceLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDashboardBuilderHref(null);
    if (!workspaceId) return;

    api
      .get<CrmConnection[]>(`/workspaces/${workspaceId}/crm/connections`)
      .then((connections) => {
        if (cancelled) return;
        const visibleConnections = connections.filter(isCustomerVisibleCrmConnection);
        const activeConnection =
          visibleConnections.find((connection) => connection.status === 'active') ??
          visibleConnections[0] ??
          null;
        setDashboardBuilderHref(
          activeConnection
            ? `/${locale}/app/connections/${activeConnection.id}/dashboard-builder`
            : null,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setDashboardBuilderHref(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [locale, workspaceId]);

  useEffect(() => {
    let cancelled = false;
    setTokenAccount(null);
    if (!workspaceId) return;

    setTokenBalanceLoading(true);
    api
      .get<TokenAccount>(`/workspaces/${workspaceId}/billing/token-account`)
      .then((account) => {
        if (!cancelled) setTokenAccount(account);
      })
      .catch(() => {
        if (!cancelled) setTokenAccount(null);
      })
      .finally(() => {
        if (!cancelled) setTokenBalanceLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const items: Item[] = [
    { href: `/${locale}/app/subscriptions`, labelKey: 'subscriptions', icon: <BadgeDollarSign className="h-4 w-4" /> },
    { href: `/${locale}/app/balance`, labelKey: 'balance', icon: <WalletCards className="h-4 w-4" /> },
    ...(dashboardBuilderHref
      ? [{ href: dashboardBuilderHref, labelKey: 'dashboardBuilder', icon: <LayoutDashboard className="h-4 w-4" /> }]
      : []),
    { href: `/${locale}/app/connections`, labelKey: 'connections', icon: <Plug className="h-4 w-4" /> },
    { href: `/${locale}/app/ai`, labelKey: 'ai', icon: <Sparkles className="h-4 w-4" /> },
    { href: `/${locale}/app/ai-chats`, labelKey: 'aiChats', icon: <MessageSquareText className="h-4 w-4" /> },
    { href: `/${locale}/app/ai-actions`, labelKey: 'aiActions', icon: <Workflow className="h-4 w-4" /> },
    { href: `/${locale}/app/knowledge-base`, labelKey: 'knowledgeBase', icon: <BookOpen className="h-4 w-4" /> },
    { href: `/${locale}/app/notifications`, labelKey: 'notifications', icon: <Bell className="h-4 w-4" /> },
    { href: `/${locale}/app/settings`, labelKey: 'settings', icon: <Settings className="h-4 w-4" /> },
  ];
  const secondaryItems: Item[] = [
    { href: `/${locale}/app/video-lessons`, labelKey: 'videoLessons', icon: <SquarePlay className="h-4 w-4" /> },
    { href: `/${locale}/app/help`, labelKey: 'help', icon: <CircleHelp className="h-4 w-4" /> },
  ];
  const subscriptionName = getSubscriptionName(tokenAccount?.plan_key, locale, t('trialPlan'));
  const subscriptionExpiry = tokenAccount?.subscription_expires_at ?? null;
  const expiryState = getSubscriptionExpiryState(subscriptionExpiry);

  return (
    <aside className="cabinet-sidebar w-full shrink-0 border-b border-border md:min-h-screen md:w-60 md:border-b-0">
      <div className="px-4 py-3 md:py-4">
        <BrandLockup />
      </div>
      <div className="cabinet-sidebar-panel mx-3 mb-2 rounded-lg px-3 py-3 md:mx-2">
        <div className="mb-3 rounded-md border border-border bg-white/80 px-2.5 py-2">
          <div className="text-xs text-muted-foreground">{t('currentSubscription')}</div>
          <div className="mt-0.5 truncate text-sm font-semibold text-foreground">
            {tokenBalanceLoading ? '…' : subscriptionName}
          </div>
          {!tokenBalanceLoading && subscriptionExpiry ? (
            <div className="mt-1 text-xs">
              <span className="text-muted-foreground">{t('subscriptionUntil')}: </span>
              <span
                className={cn(
                  'font-medium',
                  expiryState === 'soon' || expiryState === 'expired'
                    ? 'text-danger'
                    : 'text-muted-foreground',
                )}
              >
                {expiryState === 'expired' ? t('subscriptionExpired') : formatSubscriptionDate(subscriptionExpiry, locale)}
              </span>
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <WalletCards className="h-3.5 w-3.5" />
          {t('tokenBalance')}
        </div>
        <div className="mt-2 text-lg font-semibold tabular-nums text-foreground">
          {tokenBalanceLoading ? '…' : tokenAccount ? formatNumber(tokenAccount.available_tokens, locale) : '—'}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {t('reserved')}: {tokenAccount ? formatNumber(tokenAccount.reserved_tokens, locale) : '—'}
        </div>
      </div>
      <nav className="flex gap-2 overflow-x-auto px-3 py-2 md:block md:space-y-0.5 md:px-2">
        {items.map((i) => {
          const active =
            pathname === i.href ||
            (pathname.startsWith(i.href + '/') &&
              !(
                i.labelKey === 'connections' &&
                (pathname.endsWith('/dashboard') || pathname.endsWith('/dashboard-builder'))
              ));
          return (
            <Link
              key={i.href}
              href={i.href}
              className={cn(
                'flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm md:shrink md:whitespace-normal',
                active
                  ? 'cabinet-nav-link-active bg-primary/10 text-primary font-medium'
                  : 'cabinet-nav-link text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              {i.icon}
              {t(i.labelKey)}
            </Link>
          );
        })}
      </nav>
      <div className="px-3 pb-3 pt-2 md:px-2 md:pt-5">
        <div className="px-1 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground md:px-3">
          {t('other')}
        </div>
        <nav className="flex gap-2 overflow-x-auto md:block md:space-y-0.5">
          {secondaryItems.map((i) => {
            const active = pathname === i.href || pathname.startsWith(i.href + '/');
            return (
              <Link
                key={i.href}
                href={i.href}
                className={cn(
                'flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm md:shrink md:whitespace-normal',
                active
                  ? 'cabinet-nav-link-active bg-primary/10 text-primary font-medium'
                  : 'cabinet-nav-link text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
              >
                {i.icon}
                {t(i.labelKey)}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}

function getSubscriptionName(planKey: string | null | undefined, locale: string, fallback: string): string {
  const normalized = (planKey ?? '').trim().toLowerCase();
  if (!normalized || normalized === 'free' || normalized === 'paygo') return fallback;
  const plan = getPricingPlans(locale).find((item) => {
    const name = item.name.toLowerCase();
    return normalized === item.key || normalized.includes(item.key) || normalized.includes(name);
  });
  return plan?.name ?? planKey ?? fallback;
}

function getSubscriptionExpiryState(value: string | null | undefined): 'normal' | 'soon' | 'expired' | null {
  if (!value) return null;

  const expiresAt = new Date(value).getTime();
  if (Number.isNaN(expiresAt)) return null;

  const msUntilExpiry = expiresAt - Date.now();
  if (msUntilExpiry <= 0) return 'expired';

  return msUntilExpiry <= 5 * 24 * 60 * 60 * 1000 ? 'soon' : 'normal';
}

function formatSubscriptionDate(value: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(toIntlLocale(locale), { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return value;
  }
}

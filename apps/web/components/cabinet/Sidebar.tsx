'use client';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { BarChart3, LayoutDashboard, Plug, Bell, Sparkles, BookOpen, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useUserAuth } from '@/components/providers/AuthProvider';
import type { CrmConnection } from '@/lib/types';

interface Item {
  href: string;
  labelKey: string;
  icon: ReactNode;
}

export function Sidebar() {
  const t = useTranslations('cabinet.sidebar');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const pathname = usePathname() ?? '';
  const { user } = useUserAuth();
  const workspaceId = user?.workspaces?.[0]?.id ?? null;
  const [dashboardHref, setDashboardHref] = useState(`/${locale}/app/connections`);

  useEffect(() => {
    let cancelled = false;
    setDashboardHref(`/${locale}/app/connections`);
    if (!workspaceId) return;

    api
      .get<CrmConnection[]>(`/workspaces/${workspaceId}/crm/connections`)
      .then((connections) => {
        if (cancelled) return;
        const activeConnection =
          connections.find((connection) => connection.status === 'active') ?? connections[0] ?? null;
        setDashboardHref(
          activeConnection
            ? `/${locale}/app/connections/${activeConnection.id}/dashboard`
            : `/${locale}/app/connections`,
        );
      })
      .catch(() => {
        if (!cancelled) setDashboardHref(`/${locale}/app/connections`);
      });

    return () => {
      cancelled = true;
    };
  }, [locale, workspaceId]);

  const items: Item[] = [
    { href: `/${locale}/app`, labelKey: 'dashboard', icon: <LayoutDashboard className="h-4 w-4" /> },
    { href: dashboardHref, labelKey: 'analyticsDashboard', icon: <BarChart3 className="h-4 w-4" /> },
    { href: `/${locale}/app/connections`, labelKey: 'connections', icon: <Plug className="h-4 w-4" /> },
    { href: `/${locale}/app/notifications`, labelKey: 'notifications', icon: <Bell className="h-4 w-4" /> },
    { href: `/${locale}/app/ai`, labelKey: 'ai', icon: <Sparkles className="h-4 w-4" /> },
    { href: `/${locale}/app/knowledge-base`, labelKey: 'knowledgeBase', icon: <BookOpen className="h-4 w-4" /> },
    { href: `/${locale}/app/settings`, labelKey: 'settings', icon: <Settings className="h-4 w-4" /> },
  ];

  return (
    <aside className="w-56 shrink-0 border-r border-border bg-white min-h-screen">
      <div className="px-4 py-4 font-semibold flex items-center gap-2">
        <span className="inline-block h-5 w-5 rounded bg-primary" />
        {tCommon('brand')}
      </div>
      <nav className="px-2 py-2 space-y-0.5">
        {items.map((i) => {
          const active = pathname === i.href || pathname.startsWith(i.href + '/');
          return (
            <Link
              key={i.href}
              href={i.href}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-md text-sm',
                active ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              {i.icon}
              {t(i.labelKey)}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

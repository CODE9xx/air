'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { useAdminAuth } from '@/components/providers/AuthProvider';

export function AdminSidebar() {
  const t = useTranslations('admin.sidebar');
  const tAdmin = useTranslations('admin');
  const locale = useLocale();
  const pathname = usePathname() ?? '';
  const router = useRouter();
  const { logout } = useAdminAuth();

  const items = [
    { href: `/${locale}/admin`, key: 'metrics' },
    { href: `/${locale}/admin/workspaces`, key: 'workspaces' },
    { href: `/${locale}/admin/users`, key: 'users' },
    { href: `/${locale}/admin/connections`, key: 'connections' },
    { href: `/${locale}/admin/jobs`, key: 'jobs' },
    { href: `/${locale}/admin/billing`, key: 'billing' },
    { href: `/${locale}/admin/audit-logs`, key: 'auditLogs' },
    { href: `/${locale}/admin/ai-research`, key: 'aiResearch' },
  ] as const;

  const doLogout = async () => {
    await logout();
    router.push(`/${locale}/admin/login`);
  };

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-white min-h-screen flex flex-col">
      <div className="px-4 py-4 font-semibold flex items-center gap-2">
        <span className="inline-block h-5 w-5 rounded bg-danger" />
        Admin
      </div>
      <nav className="px-2 py-2 space-y-0.5 flex-1">
        {items.map((i) => {
          const active = pathname === i.href || pathname.startsWith(i.href + '/');
          return (
            <Link
              key={i.href}
              href={i.href}
              className={cn(
                'block px-3 py-2 rounded-md text-sm',
                active ? 'bg-danger/10 text-danger font-medium' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              {t(i.key)}
            </Link>
          );
        })}
      </nav>
      <button onClick={doLogout} className="m-3 text-sm text-muted-foreground hover:text-foreground text-left px-3 py-2 rounded-md hover:bg-muted">
        {tAdmin('logout')}
      </button>
    </aside>
  );
}

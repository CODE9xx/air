'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useLocale } from 'next-intl';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { PullChainThemeToggle } from '@/components/PullChainThemeToggle';

interface SupportModeState {
  active: boolean;
  support_session_id: string;
  admin_email: string;
  reason: string;
  expires_at: string;
}

export function Topbar() {
  const t = useTranslations('cabinet.topbar');
  const locale = useLocale();
  const router = useRouter();
  const { user, logout } = useUserAuth();
  const [supportMode, setSupportMode] = useState<SupportModeState | null>(null);

  useEffect(() => {
    if (user?.support_mode) {
      setSupportMode(user.support_mode);
      return;
    }
    if (typeof window === 'undefined') return;
    try {
      const raw = window.sessionStorage.getItem('code9_support_mode');
      setSupportMode(raw ? JSON.parse(raw) : null);
    } catch {
      setSupportMode(null);
    }
  }, [user?.support_mode]);

  const doLogout = async () => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem('code9_support_mode');
    }
    await logout();
    router.push(`/${locale}/login`);
  };

  return (
    <header className="cabinet-topbar flex min-h-14 flex-col items-start justify-between gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-6">
      <div className="min-w-0 text-sm text-muted-foreground">
        {t('workspace')}:{' '}
        <span className="font-medium text-foreground">
          {user?.workspaces?.[0]?.name ?? '—'}
        </span>
        {supportMode?.active && (
          <span className="mt-2 inline-flex rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800 sm:ml-3 sm:mt-0">
            Support mode · {supportMode.admin_email}
          </span>
        )}
      </div>
      <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto sm:justify-end">
        <PullChainThemeToggle />
        <LanguageSwitcher />
        <span className="text-sm text-muted-foreground hidden md:inline">{user?.email}</span>
        <button onClick={doLogout} className="text-sm text-primary hover:underline">
          {t('logout')}
        </button>
      </div>
    </header>
  );
}

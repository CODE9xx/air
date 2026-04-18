'use client';

import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useLocale } from 'next-intl';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useUserAuth } from '@/components/providers/AuthProvider';

export function Topbar() {
  const t = useTranslations('cabinet.topbar');
  const locale = useLocale();
  const router = useRouter();
  const { user, logout } = useUserAuth();

  const doLogout = async () => {
    await logout();
    router.push(`/${locale}/login`);
  };

  return (
    <header className="h-14 border-b border-border bg-white flex items-center justify-between px-6">
      <div className="text-sm text-muted-foreground">
        {t('workspace')}: <span className="text-foreground font-medium">{user?.workspaces?.[0]?.name ?? '—'}</span>
      </div>
      <div className="flex items-center gap-3">
        <LanguageSwitcher />
        <span className="text-sm text-muted-foreground hidden md:inline">{user?.email}</span>
        <button onClick={doLogout} className="text-sm text-primary hover:underline">
          {t('logout')}
        </button>
      </div>
    </header>
  );
}

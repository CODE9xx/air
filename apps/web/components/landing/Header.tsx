'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { BrandLockup } from '@/components/BrandLockup';
import { PullChainThemeToggle } from '@/components/PullChainThemeToggle';

export function Header() {
  const t = useTranslations('nav');
  const locale = useLocale();

  return (
    <header className="sticky top-0 z-40 bg-white/80 backdrop-blur border-b border-border">
      <div className="container mx-auto flex h-14 items-center justify-between gap-4">
        <Link href={`/${locale}`} className="flex items-center">
          <BrandLockup />
        </Link>
        <nav className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
          <a href="#features" className="hover:text-foreground">{t('features')}</a>
          <a href="#integrations" className="hover:text-foreground">{t('integrations')}</a>
          <a href="#pricing" className="hover:text-foreground">{t('pricing')}</a>
          <a href="#faq" className="hover:text-foreground">{t('faq')}</a>
        </nav>
        <div className="flex items-center gap-2">
          <PullChainThemeToggle />
          <LanguageSwitcher />
          <Link
            href={`/${locale}/login`}
            className="hidden sm:inline-flex items-center px-3 py-1.5 text-sm text-foreground rounded-md hover:bg-muted"
          >
            {t('login')}
          </Link>
          <Link
            href={`/${locale}/register`}
            className="inline-flex items-center px-3 py-1.5 text-sm rounded-md bg-primary text-white hover:bg-primary-700"
          >
            {t('register')}
          </Link>
        </div>
      </div>
    </header>
  );
}

'use client';

import Link from 'next/link';
import { useLocale } from 'next-intl';
import { ReactNode } from 'react';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { BrandLockup } from '@/components/BrandLockup';
import { PullChainThemeToggle } from '@/components/PullChainThemeToggle';

// Централизованный layout для страниц регистрации/логина/восстановления.
export function AuthLayout({ title, subtitle, children, footer }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const locale = useLocale();
  return (
    <div className="min-h-screen bg-muted flex flex-col">
      <header className="container mx-auto flex items-center justify-between h-14">
        <Link href={`/${locale}`} className="flex items-center">
          <BrandLockup />
        </Link>
        <div className="flex items-center gap-2">
          <PullChainThemeToggle />
          <LanguageSwitcher />
        </div>
      </header>
      <main className="flex-1 container mx-auto flex items-center justify-center py-10">
        <div className="w-full max-w-md bg-white rounded-lg border border-border shadow-soft p-8">
          <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-sm text-muted-foreground text-center">{footer}</div>}
        </div>
      </main>
    </div>
  );
}

'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { BrandLockup } from '@/components/BrandLockup';

export function Footer() {
  const t = useTranslations('footer');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const legalLinks = [
    { href: `/${locale}/legal`, label: t('legal') },
    { href: `/${locale}/terms`, label: t('terms') },
    { href: `/${locale}/privacy`, label: t('privacy') },
    { href: `/${locale}/personal-data`, label: t('dpa') },
  ];

  return (
    <footer className="border-t border-border bg-white">
      <div className="container mx-auto py-10 grid md:grid-cols-4 gap-6 text-sm">
        <div>
          <BrandLockup />
          <p className="mt-3 text-muted-foreground">{tCommon('tagline')}</p>
        </div>
        <div>
          <div className="font-medium mb-3">{t('legal')}</div>
          <ul className="space-y-2 text-muted-foreground">
            {legalLinks.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="transition hover:text-foreground">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        {t('copyright', { year: new Date().getFullYear() })}
      </div>
    </footer>
  );
}

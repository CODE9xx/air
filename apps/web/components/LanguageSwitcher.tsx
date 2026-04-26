'use client';

import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from 'next/navigation';
import { locales } from '@/i18n/routing';
import { cn } from '@/lib/utils';

// Переключатель локали. Меняет первый сегмент пути: /ru/... → /en/...
export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations('common');
  const current = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const switchTo = (locale: string) => {
    if (!pathname) return;
    const parts = pathname.split('/');
    // /ru/xxx → parts = ['', 'ru', 'xxx']
    if (parts.length > 1 && (locales as readonly string[]).includes(parts[1])) {
      parts[1] = locale;
    } else {
      parts.splice(1, 0, locale);
    }
    router.push(parts.join('/') || `/${locale}`);
  };

  return (
    <div className={cn('inline-flex rounded-md border border-border bg-white', className)} aria-label={t('language')}>
      {locales.map((loc, index) => (
        <button
          key={loc}
          type="button"
          onClick={() => switchTo(loc)}
          className={cn(
            'px-2.5 py-1 text-xs font-medium uppercase tracking-wide',
            current === loc ? 'bg-primary text-white' : 'text-muted-foreground hover:text-foreground',
            index === 0 && 'rounded-l-md',
            index === locales.length - 1 && 'rounded-r-md',
          )}
          aria-pressed={current === loc}
        >
          {loc}
        </button>
      ))}
    </div>
  );
}

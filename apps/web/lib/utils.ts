import clsx, { type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// shadcn-style classname merger.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function toIntlLocale(locale: string = 'ru'): string {
  if (locale === 'ru' || locale.startsWith('ru-')) return 'ru-RU';
  if (locale === 'es' || locale.startsWith('es-')) return 'es-ES';
  return 'en-US';
}

export function formatDate(value: string | null | undefined, locale: string = 'ru'): string {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat(toIntlLocale(locale), {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function formatMoney(cents: number, currency: string = 'RUB', locale: string = 'ru'): string {
  try {
    return new Intl.NumberFormat(toIntlLocale(locale), {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(cents / 100);
  } catch {
    return `${(cents / 100).toFixed(0)} ${currency}`;
  }
}

export function formatNumber(value: number, locale: string = 'ru'): string {
  return new Intl.NumberFormat(toIntlLocale(locale)).format(value);
}

// Конфигурация локализации для next-intl.
export const locales = ['ru', 'en', 'es'] as const;
export const defaultLocale = 'ru' as const;

export type Locale = (typeof locales)[number];

export function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}

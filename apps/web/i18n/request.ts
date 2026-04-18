import { getRequestConfig } from 'next-intl/server';
import { defaultLocale, isLocale } from './routing';

// next-intl загружает messages/{locale}.json по текущему сегменту URL.
export default getRequestConfig(async ({ locale }) => {
  const finalLocale = isLocale(locale ?? '') ? locale! : defaultLocale;
  return {
    locale: finalLocale,
    messages: (await import(`../messages/${finalLocale}.json`)).default,
  };
});

import { NextIntlClientProvider } from 'next-intl';
import { getMessages, unstable_setRequestLocale } from 'next-intl/server';
import { notFound } from 'next/navigation';
import type { ReactNode } from 'react';
import { isLocale, locales } from '@/i18n/routing';
import { ToastProvider } from '@/components/ui/Toast';
import { UserAuthProvider, AdminAuthProvider } from '@/components/providers/AuthProvider';

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: { locale: string };
}) {
  const { locale } = params;
  if (!isLocale(locale)) notFound();
  unstable_setRequestLocale(locale);

  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <UserAuthProvider>
            <AdminAuthProvider>
              <ToastProvider>{children}</ToastProvider>
            </AdminAuthProvider>
          </UserAuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

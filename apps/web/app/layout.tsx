// Root layout — next-intl перехватывает маршруты в middleware и редиректит
// на /ru или /en, так что реально рендерится [locale]/layout.tsx c <html> тегом.
// Этот файл обязан существовать для App Router.
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'CODE9 Analytics',
  description: 'CRM-аудит, выгрузки и AI-аналитика для amoCRM / Kommo / Bitrix24.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}

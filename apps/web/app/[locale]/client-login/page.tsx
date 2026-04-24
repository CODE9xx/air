'use client';

import { useEffect } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { LoginForm } from '@/components/forms/LoginForm';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Spinner } from '@/components/ui/Spinner';

export default function ClientLoginPage() {
  const t = useTranslations('auth.login');
  const locale = useLocale();
  const router = useRouter();
  const { user, ready } = useUserAuth();

  useEffect(() => {
    if (ready && user) {
      router.replace(`/${locale}/app/connections/new`);
    }
  }, [ready, user, router, locale]);

  if (ready && user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted">
        <Spinner size={24} />
      </div>
    );
  }

  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <LoginForm redirectTo={`/${locale}/app/connections/new`} />
    </AuthLayout>
  );
}

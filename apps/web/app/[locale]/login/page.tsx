'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { LoginForm } from '@/components/forms/LoginForm';

export default function LoginPage() {
  const t = useTranslations('auth.login');
  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <LoginForm />
    </AuthLayout>
  );
}

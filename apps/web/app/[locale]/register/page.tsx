'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { RegisterForm } from '@/components/forms/RegisterForm';

export default function RegisterPage() {
  const t = useTranslations('auth.register');
  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <RegisterForm />
    </AuthLayout>
  );
}

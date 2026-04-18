'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { ForgotPasswordForm } from '@/components/forms/ForgotPasswordForm';

export default function ForgotPasswordPage() {
  const t = useTranslations('auth.forgotPassword');
  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <ForgotPasswordForm />
    </AuthLayout>
  );
}

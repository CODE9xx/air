'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { ResetPasswordForm } from '@/components/forms/ResetPasswordForm';

export default function ResetPasswordPage() {
  const t = useTranslations('auth.resetPassword');
  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <ResetPasswordForm />
    </AuthLayout>
  );
}

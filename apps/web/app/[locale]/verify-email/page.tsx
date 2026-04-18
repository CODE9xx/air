'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { VerifyEmailForm } from '@/components/forms/VerifyEmailForm';

export default function VerifyEmailPage() {
  const t = useTranslations('auth.verifyEmail');
  return (
    <AuthLayout title={t('title')}>
      <VerifyEmailForm />
    </AuthLayout>
  );
}

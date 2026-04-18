'use client';

import { useTranslations } from 'next-intl';
import { AuthLayout } from '@/components/forms/AuthLayout';
import { AdminLoginForm } from '@/components/forms/AdminLoginForm';

export default function AdminLoginPage() {
  const t = useTranslations('admin.login');
  return (
    <AuthLayout title={t('title')} subtitle={t('subtitle')}>
      <AdminLoginForm />
    </AuthLayout>
  );
}

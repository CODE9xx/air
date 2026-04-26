'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import { useState } from 'react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({ email: z.string().email() });
type FormValues = z.infer<typeof schema>;

export function ForgotPasswordForm() {
  const t = useTranslations('auth.forgotPassword');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const { toast } = useToast();
  const [sent, setSent] = useState(false);
  const [sentEmail, setSentEmail] = useState('');

  const {
    register,
    getValues,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      const email = values.email.trim().toLowerCase();
      await api.post('/auth/password-reset/request', { email }, { scope: 'public' });
      setSentEmail(email);
      setSent(true);
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    }
  };

  if (sent) {
    const email = sentEmail || getValues('email') || '';
    return (
      <div>
        <p className="text-sm text-muted-foreground">{t('sent')}</p>
        <Link
          href={`/${locale}/reset-password${email ? `?email=${encodeURIComponent(email)}` : ''}`}
          className="mt-4 inline-block text-primary hover:underline"
        >
          {rootT('common.continue')}
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div>
        <label className="label">{t('email')}</label>
        <Input type="email" {...register('email')} error={errors.email && tErr('invalidEmail')} />
      </div>
      <Button type="submit" loading={isSubmitting} className="w-full">
        {t('submit')}
      </Button>
      <Link href={`/${locale}/login`} className="block text-center text-sm text-primary hover:underline">
        {t('backToLogin')}
      </Link>
    </form>
  );
}

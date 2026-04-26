'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({
  email: z.string().email(),
  code: z.string().length(6),
  new_password: z.string().min(8),
});
type FormValues = z.infer<typeof schema>;

export function ResetPasswordForm() {
  const t = useTranslations('auth.resetPassword');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const [resending, setResending] = useState(false);
  const initialEmail = searchParams.get('email') ?? '';

  const {
    register,
    handleSubmit,
    trigger,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: initialEmail },
  });

  const onSubmit = async (values: FormValues) => {
    try {
      await api.post(
        '/auth/password-reset/confirm',
        { ...values, email: values.email.trim().toLowerCase() },
        { scope: 'public' },
      );
      toast({ kind: 'success', title: t('success') });
      router.push(`/${locale}/login`);
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    }
  };

  const resendCode = async () => {
    const emailValid = await trigger('email');
    if (!emailValid) return;

    setResending(true);
    try {
      await api.post(
        '/auth/password-reset/request',
        { email: watch('email').trim().toLowerCase() },
        { scope: 'public' },
      );
      toast({ kind: 'info', title: t('resent') });
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    } finally {
      setResending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div>
        <label className="label">{t('email')}</label>
        <Input type="email" {...register('email')} error={errors.email && tErr('invalidEmail')} />
        <p className="mt-2 text-xs text-muted-foreground">{t('emailHint')}</p>
      </div>
      <div>
        <label className="label">{t('code')}</label>
        <Input maxLength={6} {...register('code')} error={errors.code && tErr('codeLength')} />
      </div>
      <div>
        <label className="label">{t('newPassword')}</label>
        <Input type="password" {...register('new_password')} error={errors.new_password && tErr('passwordTooShort')} />
      </div>
      <Button type="submit" loading={isSubmitting} className="w-full">
        {t('submit')}
      </Button>
      <button
        type="button"
        onClick={resendCode}
        disabled={isSubmitting || resending}
        className="block w-full text-center text-sm font-medium text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50"
      >
        {resending ? t('resending') : t('resend')}
      </button>
    </form>
  );
}

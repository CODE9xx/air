'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});
type FormValues = z.infer<typeof schema>;

export function RegisterForm() {
  const t = useTranslations('auth.register');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      await api.post('/auth/register', { email: values.email, password: values.password, locale }, { scope: 'public' });
      router.push(`/${locale}/verify-email?email=${encodeURIComponent(values.email)}`);
    } catch (err) {
      const key = mapAuthErrorKey(err);
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(key) });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div>
        <label className="label">{t('email')}</label>
        <Input type="email" autoComplete="email" {...register('email')} error={errors.email && tErr('invalidEmail')} />
      </div>
      <div>
        <label className="label">{t('password')}</label>
        <Input type="password" autoComplete="new-password" {...register('password')} error={errors.password && tErr('passwordTooShort')} />
        <p className="mt-1 text-xs text-muted-foreground">{t('passwordHint')}</p>
      </div>
      <Button type="submit" loading={isSubmitting} className="w-full">
        {t('submit')}
      </Button>
      <div className="text-sm text-muted-foreground text-center">
        {t('alreadyHaveAccount')}{' '}
        <Link href={`/${locale}/login`} className="text-primary hover:underline">
          {t('loginLink')}
        </Link>
      </div>
    </form>
  );
}

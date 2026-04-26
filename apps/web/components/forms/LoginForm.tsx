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
import { userTokenStore } from '@/lib/auth';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';
import type { User } from '@/lib/types';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});
type FormValues = z.infer<typeof schema>;

interface LoginResponse {
  access_token: string;
  user: User;
}

interface LoginFormProps {
  redirectTo?: string;
}

export function LoginForm({ redirectTo }: LoginFormProps = {}) {
  const t = useTranslations('auth.login');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { setUser } = useUserAuth();
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      const res = await api.post<LoginResponse>('/auth/login', values, { scope: 'public' });
      userTokenStore.set(res.access_token);
      const currentUser = await api.get<User>('/auth/me').catch(() => res.user);
      setUser(currentUser);
      router.push(redirectTo ?? `/${locale}/app`);
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
        <Input type="password" autoComplete="current-password" {...register('password')} error={errors.password && tErr('passwordTooShort')} />
      </div>
      <div className="flex justify-end -mt-2">
        <Link href={`/${locale}/forgot-password`} className="text-xs text-primary hover:underline">
          {t('forgotPassword')}
        </Link>
      </div>
      <Button type="submit" loading={isSubmitting} className="w-full">
        {t('submit')}
      </Button>
      <div className="text-sm text-muted-foreground text-center">
        {t('noAccount')}{' '}
        <Link href={`/${locale}/register`} className="text-primary hover:underline">
          {t('registerLink')}
        </Link>
      </div>
    </form>
  );
}

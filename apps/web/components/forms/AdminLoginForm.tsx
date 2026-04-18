'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { adminTokenStore } from '@/lib/auth';
import { useAdminAuth } from '@/components/providers/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});
type FormValues = z.infer<typeof schema>;

interface AdminLoginResponse {
  access_token: string;
  admin: { id: string; email: string; role: 'superadmin' | 'support' };
}

export function AdminLoginForm() {
  const t = useTranslations('admin.login');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { setAdmin } = useAdminAuth();
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      const res = await api.post<AdminLoginResponse>('/admin/auth/login', values, { scope: 'public' });
      adminTokenStore.set(res.access_token);
      setAdmin(res.admin);
      router.push(`/${locale}/admin`);
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
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
      <Button type="submit" loading={isSubmitting} className="w-full">
        {t('submit')}
      </Button>
    </form>
  );
}

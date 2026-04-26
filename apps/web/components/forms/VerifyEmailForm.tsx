'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({
  code: z.string().length(6),
});
type FormValues = z.infer<typeof schema>;

export function VerifyEmailForm() {
  const t = useTranslations('auth.verifyEmail');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const email = params?.get('email') ?? '';
  const { toast } = useToast();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    if (!email) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT('auth.errors.generic') });
      return;
    }
    try {
      await api.post('/auth/verify-email', { email, code: values.code }, { scope: 'public' });
      toast({ kind: 'success', title: rootT('common.success') });
      router.push(`/${locale}/login`);
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    }
  };

  const resend = async () => {
    if (!email) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT('auth.errors.generic') });
      return;
    }
    try {
      await api.post('/auth/verify-email/resend', { email }, { scope: 'public' });
      toast({ kind: 'info', title: t('resent') });
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    }
  };

  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">{t('subtitle', { email: email || '—' })}</p>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div>
          <label className="label">{t('code')}</label>
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            {...register('code')}
            error={errors.code && tErr('codeLength')}
          />
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">
          {t('submit')}
        </Button>
      </form>
      <button type="button" onClick={resend} className="mt-4 text-sm text-primary hover:underline">
        {t('resend')}
      </button>
    </>
  );
}

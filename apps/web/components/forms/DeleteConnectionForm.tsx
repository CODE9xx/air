'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Dialog } from '@/components/ui/Dialog';
import { api } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { mapAuthErrorKey } from './mapApiError';

const schema = z.object({ code: z.string().length(6) });
type FormValues = z.infer<typeof schema>;

export function DeleteConnectionForm({ connectionId }: { connectionId: string }) {
  const t = useTranslations('cabinet.connections.delete');
  const tErr = useTranslations('auth.errors');
  const rootT = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();

  const [step, setStep] = useState<'warning' | 'code'>('warning');
  const [requesting, setRequesting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const requestCode = async () => {
    setRequesting(true);
    try {
      await api.post(`/crm/connections/${connectionId}/delete/request`);
      toast({ kind: 'info', title: t('codeSent') });
      setStep('code');
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    } finally {
      setRequesting(false);
    }
  };

  const confirm = async (values: FormValues) => {
    try {
      await api.post(`/crm/connections/${connectionId}/delete/confirm`, { code: values.code });
      toast({ kind: 'success', title: rootT('common.success') });
      router.push(`/${locale}/app/connections`);
    } catch (err) {
      toast({ kind: 'error', title: rootT('common.error'), description: rootT(mapAuthErrorKey(err)) });
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="rounded-md border border-danger bg-red-50 p-4 text-sm text-red-900">
        {t('warning')}
      </div>

      <Button variant="danger" onClick={requestCode} loading={requesting}>
        {t('requestCode')}
      </Button>

      <Dialog open={step === 'code'} onClose={() => setStep('warning')} title={t('enterCode')}>
        <form onSubmit={handleSubmit(confirm)} className="space-y-4" noValidate>
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            {...register('code')}
            error={errors.code && tErr('codeLength')}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setStep('warning')}>
              {rootT('common.cancel')}
            </Button>
            <Button type="submit" variant="danger" loading={isSubmitting}>
              {t('confirm')}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

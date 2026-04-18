'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/lib/api';
import type { CrmConnection } from '@/lib/types';
import { useToast } from '@/components/ui/Toast';

export default function NewConnectionPage() {
  const t = useTranslations('cabinet.connections.new');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);

  const connectMock = async () => {
    setLoading(true);
    try {
      const res = await api.post<CrmConnection>('/crm/connections/mock-amocrm');
      router.push(`/${locale}/app/connections/${res.id}`);
    } catch {
      toast({ kind: 'error', title: tCommon('error') });
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="card p-5 flex flex-col">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-primary/10 text-primary font-semibold">
            am
          </div>
          <h3 className="mt-3 font-semibold">{t('amocrm')}</h3>
          <p className="text-xs text-muted-foreground mt-1 flex-1">{t('amocrmDesc')}</p>
          <Button onClick={connectMock} loading={loading} className="mt-4">
            {t('connectMock')}
          </Button>
        </div>

        <div className="card p-5 opacity-80">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-muted text-muted-foreground font-semibold">
            ko
          </div>
          <h3 className="mt-3 font-semibold">Kommo</h3>
          <p className="text-xs text-muted-foreground mt-1">{t('kommoDesc')}</p>
          <Badge tone="neutral" className="mt-4">{tCommon('comingSoon')}</Badge>
        </div>

        <div className="card p-5 opacity-80">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded bg-muted text-muted-foreground font-semibold">
            bx
          </div>
          <h3 className="mt-3 font-semibold">Bitrix24</h3>
          <p className="text-xs text-muted-foreground mt-1">{t('bitrixDesc')}</p>
          <Badge tone="neutral" className="mt-4">{tCommon('comingSoon')}</Badge>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{t('mockNote')}</p>
    </div>
  );
}

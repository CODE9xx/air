'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { api } from '@/lib/api';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function AIPage() {
  const t = useTranslations('cabinet.ai');
  const tConnections = useTranslations('cabinet.connections');
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;

  const [consent, setConsent] = useState<string>('not_accepted');

  useEffect(() => {
    if (!wsId) return;
    (async () => {
      try {
        const res = await api.get<{ status: string }>(`/workspaces/${wsId}/ai/consent`);
        setConsent(res.status);
      } catch {
        // no-op
      }
    })();
  }, [wsId]);

  const accept = async () => {
    if (!wsId) return;
    await api.post(`/workspaces/${wsId}/ai/consent`, { action: 'accept', terms_version: 'v1' });
    setConsent('accepted');
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>
      {!wsId && <EmptyState title={tConnections('noWorkspaceTitle')} description={tConnections('noWorkspaceBody')} />}
      {wsId && consent !== 'accepted' && (
        <div className="card p-6">
          <p className="text-sm">{t('consentRequired')}</p>
          <Button onClick={accept} className="mt-4">{t('accept')}</Button>
        </div>
      )}
      {wsId && consent === 'accepted' && <EmptyState title={t('empty')} />}
    </div>
  );
}

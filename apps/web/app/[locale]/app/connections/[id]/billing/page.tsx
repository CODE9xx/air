'use client';

import { useTranslations } from 'next-intl';
import { BillingPanel } from '@/components/cabinet/BillingPanel';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { EmptyState } from '@/components/ui/EmptyState';

export default function ConnectionBillingPage() {
  const t = useTranslations('cabinet.connections');
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  if (!wsId) {
    return <EmptyState title={t('noWorkspaceTitle')} description={t('noWorkspaceBody')} />;
  }
  return <BillingPanel workspaceId={wsId} />;
}

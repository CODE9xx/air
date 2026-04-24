'use client';

import { useTranslations } from 'next-intl';
import { NotificationsList } from '@/components/cabinet/NotificationsList';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { EmptyState } from '@/components/ui/EmptyState';

export default function NotificationsPage() {
  const t = useTranslations('cabinet.notifications');
  const tConnections = useTranslations('cabinet.connections');
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      {wsId ? (
        <NotificationsList workspaceId={wsId} />
      ) : (
        <EmptyState title={tConnections('noWorkspaceTitle')} description={tConnections('noWorkspaceBody')} />
      )}
    </div>
  );
}

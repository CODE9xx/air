'use client';

import { useTranslations } from 'next-intl';
import { NotificationsList } from '@/components/cabinet/NotificationsList';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function NotificationsPage() {
  const t = useTranslations('cabinet.notifications');
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <NotificationsList workspaceId={wsId} />
    </div>
  );
}

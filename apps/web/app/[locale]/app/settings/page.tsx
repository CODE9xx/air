'use client';

import { useTranslations } from 'next-intl';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function CabinetSettingsPage() {
  const t = useTranslations('cabinet.settings');
  const { user } = useUserAuth();
  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="card p-6 space-y-4">
        <h2 className="font-semibold">{t('profile')}</h2>
        <Field label={t('email')} value={user?.email ?? '—'} />
        <Field label={t('displayName')} value={user?.display_name ?? '—'} />
        <Field label={t('locale')} value={user?.locale ?? 'ru'} />
      </div>
      <div className="card p-6 space-y-4">
        <h2 className="font-semibold">{t('workspace')}</h2>
        <Field label={t('workspaceName')} value={user?.workspaces?.[0]?.name ?? '—'} />
      </div>
      <div className="card p-6 border border-danger bg-red-50">
        <h2 className="font-semibold text-danger">{t('dangerZone')}</h2>
        <p className="text-sm text-muted-foreground mt-2">{t('deleteAccount')}</p>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

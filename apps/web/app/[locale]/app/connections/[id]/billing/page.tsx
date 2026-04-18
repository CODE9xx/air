'use client';

import { BillingPanel } from '@/components/cabinet/BillingPanel';
import { useUserAuth } from '@/components/providers/AuthProvider';

export default function ConnectionBillingPage() {
  const { user } = useUserAuth();
  const wsId = user?.workspaces?.[0]?.id ?? 'ws-demo-1';
  return <BillingPanel workspaceId={wsId} />;
}

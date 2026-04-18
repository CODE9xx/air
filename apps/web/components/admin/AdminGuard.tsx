'use client';

import { useEffect } from 'react';
import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/components/providers/AuthProvider';
import { adminTokenStore } from '@/lib/auth';
import { USE_MOCK_API } from '@/lib/env';
import { api } from '@/lib/api';

// В mock-режиме auto-login для удобства разработки.
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { admin, setAdmin } = useAdminAuth();
  const locale = useLocale();
  const router = useRouter();

  useEffect(() => {
    if (admin) return;
    if (USE_MOCK_API) {
      (async () => {
        try {
          const res = await api.post<{ access_token: string; admin: { id: string; email: string; role: 'superadmin' | 'support' } }>(
            '/admin/auth/login',
            { email: 'admin@code9.app', password: 'adminpass' },
            { scope: 'public' },
          );
          adminTokenStore.set(res.access_token);
          setAdmin(res.admin);
        } catch {
          router.replace(`/${locale}/admin/login`);
        }
      })();
    } else {
      router.replace(`/${locale}/admin/login`);
    }
  }, [admin, locale, router, setAdmin]);

  if (!admin) {
    return null;
  }
  return <>{children}</>;
}

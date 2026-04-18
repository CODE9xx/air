'use client';

import { useEffect } from 'react';
import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Spinner } from '@/components/ui/Spinner';

// Guard: проверяет залогинен ли пользователь. Иначе → /login.
// В mock-режиме автоматически «логинит» demo-пользователя чтобы упростить локальный dev.
import { USE_MOCK_API } from '@/lib/env';
import { userTokenStore } from '@/lib/auth';
import type { User } from '@/lib/types';
import { api } from '@/lib/api';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, ready, setUser } = useUserAuth();
  const locale = useLocale();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (user) return;

    if (USE_MOCK_API) {
      // Для удобства локального DX — молча создаём demo-сессию.
      (async () => {
        try {
          const res = await api.post<{ access_token: string; user: User }>(
            '/auth/login',
            { email: 'demo@code9.app', password: 'demopass' },
            { scope: 'public' },
          );
          userTokenStore.set(res.access_token);
          setUser(res.user);
        } catch {
          router.replace(`/${locale}/login`);
        }
      })();
      return;
    }

    router.replace(`/${locale}/login`);
  }, [ready, user, router, locale, setUser]);

  if (!ready || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size={24} />
      </div>
    );
  }
  return <>{children}</>;
}

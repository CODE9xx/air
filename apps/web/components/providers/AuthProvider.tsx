'use client';

import { createContext, useContext, useEffect, useMemo, useState, ReactNode, useCallback } from 'react';
import { api, ApiError } from '@/lib/api';
import { adminTokenStore, userTokenStore } from '@/lib/auth';
import type { AdminUser, User } from '@/lib/types';

interface UserAuthValue {
  user: User | null;
  ready: boolean;
  setUser: (u: User | null) => void;
  setAccessToken: (token: string | null) => void;
  logout: () => Promise<void>;
}

const UserAuthContext = createContext<UserAuthValue | null>(null);

export function UserAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Попытка восстановить сессию: refresh → /auth/me. Если не вышло — просто остаёмся без user.
    let cancelled = false;
    (async () => {
      try {
        // В mock-режиме /auth/me вернёт ошибку, если не логинились — это ок.
        const me = await api.get<User>('/auth/me');
        if (!cancelled) setUser(me);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          // no-op, пользователь не залогинен
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setAccessToken = useCallback((token: string | null) => {
    userTokenStore.set(token);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // игнорируем
    }
    userTokenStore.clear();
    setUser(null);
  }, []);

  const value = useMemo<UserAuthValue>(
    () => ({ user, ready, setUser, setAccessToken, logout }),
    [user, ready, setAccessToken, logout],
  );

  return <UserAuthContext.Provider value={value}>{children}</UserAuthContext.Provider>;
}

export function useUserAuth(): UserAuthValue {
  const ctx = useContext(UserAuthContext);
  if (!ctx) throw new Error('useUserAuth must be inside <UserAuthProvider>');
  return ctx;
}

// --- Admin context (отдельный) ---

interface AdminAuthValue {
  admin: AdminUser | null;
  setAdmin: (a: AdminUser | null) => void;
  setAccessToken: (token: string | null) => void;
  logout: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthValue | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<AdminUser | null>(null);

  const setAccessToken = useCallback((token: string | null) => {
    adminTokenStore.set(token);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/admin/auth/logout', undefined, { scope: 'admin' });
    } catch {
      // игнор
    }
    adminTokenStore.clear();
    setAdmin(null);
  }, []);

  const value = useMemo<AdminAuthValue>(
    () => ({ admin, setAdmin, setAccessToken, logout }),
    [admin, setAccessToken, logout],
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth(): AdminAuthValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error('useAdminAuth must be inside <AdminAuthProvider>');
  return ctx;
}

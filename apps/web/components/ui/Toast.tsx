'use client';

import { createContext, useCallback, useContext, useState, ReactNode } from 'react';
import type { ToastMessage } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ToastContextValue {
  toast: (t: Omit<ToastMessage, 'id'>) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMessage[]>([]);

  const toast = useCallback((t: Omit<ToastMessage, 'id'>) => {
    const id = Math.random().toString(36).slice(2);
    const msg: ToastMessage = { id, ...t };
    setItems((prev) => [...prev, msg]);
    setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== id)), 4500);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed top-4 right-4 z-[60] flex flex-col gap-2 w-[320px] max-w-[90vw]">
        {items.map((i) => (
          <div
            key={i.id}
            className={cn(
              'rounded-md border shadow-soft px-4 py-3 bg-white',
              i.kind === 'error' && 'border-danger',
              i.kind === 'success' && 'border-success',
              i.kind === 'warning' && 'border-warning',
              i.kind === 'info' && 'border-border',
            )}
          >
            <div className="text-sm font-medium text-foreground">{i.title}</div>
            {i.description && <div className="text-xs text-muted-foreground mt-1">{i.description}</div>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}

'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { AdminSidebar } from '@/components/admin/AdminSidebar';
import { AdminGuard } from '@/components/admin/AdminGuard';

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  // На /admin/login layout без sidebar/guard.
  if (pathname.endsWith('/admin/login')) {
    return <>{children}</>;
  }
  return (
    <AdminGuard>
      <div className="flex min-h-screen bg-muted">
        <AdminSidebar />
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </AdminGuard>
  );
}

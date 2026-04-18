import { ReactNode } from 'react';
import { Sidebar } from '@/components/cabinet/Sidebar';
import { Topbar } from '@/components/cabinet/Topbar';
import { AuthGuard } from '@/components/cabinet/AuthGuard';

export default function CabinetLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen bg-muted">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="flex-1 p-6 overflow-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}

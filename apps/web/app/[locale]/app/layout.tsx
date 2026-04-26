import { ReactNode } from 'react';
import { Sidebar } from '@/components/cabinet/Sidebar';
import { Topbar } from '@/components/cabinet/Topbar';
import { AuthGuard } from '@/components/cabinet/AuthGuard';

export default function CabinetLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <div className="cabinet-shell flex min-h-screen flex-col md:flex-row">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="cabinet-main flex-1 overflow-auto p-4 sm:p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}

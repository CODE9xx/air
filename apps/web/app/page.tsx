import { redirect } from 'next/navigation';

// Fallback: если middleware не сработал, редиректим на дефолтную локаль.
export default function RootPage() {
  redirect('/ru');
}

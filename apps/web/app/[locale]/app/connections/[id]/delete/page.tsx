'use client';

import { useParams } from 'next/navigation';
import { DeleteConnectionForm } from '@/components/forms/DeleteConnectionForm';

export default function DeleteConnectionPage() {
  const params = useParams<{ id: string }>();
  if (!params?.id) return null;
  return <DeleteConnectionForm connectionId={params.id} />;
}

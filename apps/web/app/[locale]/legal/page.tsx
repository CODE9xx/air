import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';
import { getLegalDocument } from '@/lib/legal';

export default function LegalPage({ params }: { params: { locale: string } }) {
  return <LegalDocumentPage locale={params.locale} document={getLegalDocument(params.locale, 'legal')} />;
}

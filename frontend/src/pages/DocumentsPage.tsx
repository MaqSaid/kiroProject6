import { type FC } from 'react';
import { DocumentUpload } from '@/components/DocumentUpload';
import { DocumentList } from '@/components/DocumentList';

export const DocumentsPage: FC = () => {
  return (
    <section aria-label="Document management" className="space-y-8">
      <DocumentUpload />
      <DocumentList />
    </section>
  );
};

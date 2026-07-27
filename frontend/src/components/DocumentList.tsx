import { type FC, useMemo } from 'react';
import { useDocuments } from '@/hooks/useDocuments';
import { ErrorState } from '@/components/ErrorState';

export const DocumentList: FC = () => {
  const { data, isLoading, isError, error, refetch } = useDocuments();

  const sortedDocuments = useMemo(() => {
    const documents = data?.documents ?? [];
    return [...documents].sort(
      (a, b) => new Date(b.ingestion_date).getTime() - new Date(a.ingestion_date).getTime(),
    );
  }, [data?.documents]);

  if (isLoading) {
    return (
      <section aria-label="Documents list" aria-busy="true" className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">Ingested Documents</h2>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-200 rounded-lg" />
          ))}
        </div>
      </section>
    );
  }

  if (isError) {
    return (
      <section aria-label="Documents list" className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">Ingested Documents</h2>
        <ErrorState
          message={error?.message ?? 'Failed to load documents'}
          onRetry={() => void refetch()}
        />
      </section>
    );
  }

  return (
    <section aria-label="Documents list" className="space-y-3">
      <h2 className="text-lg font-semibold text-gray-900">Ingested Documents</h2>

      {sortedDocuments.length === 0 ? (
        <p className="text-sm text-gray-500 py-8 text-center">
          No documents ingested yet. Upload a document to get started.
        </p>
      ) : (
        <ul className="space-y-2" aria-label="List of ingested documents">
          {sortedDocuments.map((doc) => (
            <li
              key={doc.document_id}
              className="flex items-center justify-between rounded-lg border border-gray-200 p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {doc.filename}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {doc.format.toUpperCase()} · {new Date(doc.ingestion_date).toLocaleDateString()}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

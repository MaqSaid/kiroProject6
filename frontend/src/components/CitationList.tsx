import { type FC } from 'react';
import type { Citation } from '@/types/api';

interface CitationListProps {
  citations: Citation[];
  onCitationClick?: (index: number) => void;
}

function getStatusBadge(status: Citation['verification_status']): string {
  switch (status) {
    case 'verified':
      return 'bg-green-100 text-green-800';
    case 'partial':
      return 'bg-amber-100 text-amber-800';
    case 'unsupported':
      return 'bg-red-100 text-red-800';
  }
}

export const CitationList: FC<CitationListProps> = ({ citations, onCitationClick }) => {
  if (citations.length === 0) return null;

  return (
    <section aria-label="Citations" className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-900">Citations</h3>
      <ol className="space-y-2">
        {citations.map((citation) => (
          <li key={citation.index} className="flex items-start gap-2">
            <button
              type="button"
              onClick={() => onCitationClick?.(citation.index)}
              className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-2 py-1 text-sm font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-safe:transition-colors"
              aria-label={`View source for citation ${citation.index}`}
            >
              [{citation.index}]
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-700 break-words">{citation.claim}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-gray-500 truncate">
                  {citation.source_reference}
                </span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${getStatusBadge(citation.verification_status)}`}
                >
                  {citation.verification_status}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
};

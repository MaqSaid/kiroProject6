import { type FC } from 'react';
import type { FallbackInfo } from '@/types/api';

interface FallbackDisplayProps {
  fallbackInfo: FallbackInfo;
}

export const FallbackDisplay: FC<FallbackDisplayProps> = ({ fallbackInfo }) => {
  const { found_topics, not_found_topics, suggested_documents } = fallbackInfo;

  return (
    <section
      aria-label="Fallback information"
      data-testid="fallback-display"
      className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3"
      role="status"
    >
      <p className="text-sm font-semibold text-amber-800">
        Unable to provide a confident answer
      </p>

      {found_topics.length > 0 && (
        <div data-testid="fallback-found-topics">
          <h4 className="text-xs font-medium text-amber-700 uppercase mb-1">
            Topics found
          </h4>
          <ul aria-label="Found topics" className="flex flex-wrap gap-1">
            {found_topics.map((topic) => (
              <li
                key={topic}
                className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded-full"
              >
                {topic}
              </li>
            ))}
          </ul>
        </div>
      )}

      {not_found_topics.length > 0 && (
        <div data-testid="fallback-not-found-topics">
          <h4 className="text-xs font-medium text-amber-700 uppercase mb-1">
            Topics not found
          </h4>
          <ul aria-label="Topics not found" className="flex flex-wrap gap-1">
            {not_found_topics.map((topic) => (
              <li
                key={topic}
                className="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full"
              >
                {topic}
              </li>
            ))}
          </ul>
        </div>
      )}

      {suggested_documents.length > 0 && (
        <div data-testid="fallback-suggested-documents">
          <h4 className="text-xs font-medium text-amber-700 uppercase mb-1">
            Suggested documents for manual consultation
          </h4>
          <ul aria-label="Suggested documents" className="space-y-1">
            {suggested_documents.map((doc) => (
              <li
                key={doc}
                className="text-sm text-amber-900 flex items-center gap-1"
              >
                <span aria-hidden="true" className="text-amber-600">📄</span>
                {doc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};

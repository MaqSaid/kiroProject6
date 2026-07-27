import { type FC } from 'react';
import type { SourceChunk } from '@/types/api';

interface SearchResultsProps {
  chunks: SourceChunk[];
  highlightedIndex?: number;
}

function getMethodBadge(method: SourceChunk['retrieval_method']): string {
  switch (method) {
    case 'dense':
      return 'bg-purple-100 text-purple-800';
    case 'sparse':
      return 'bg-sky-100 text-sky-800';
    case 'graph':
      return 'bg-emerald-100 text-emerald-800';
  }
}

export const SearchResults: FC<SearchResultsProps> = ({ chunks, highlightedIndex }) => {
  if (chunks.length === 0) return null;

  return (
    <section aria-label="Source chunks" className="space-y-3">
      <h3 className="text-sm font-semibold text-gray-900">Sources</h3>
      <ul className="space-y-2" aria-label="Retrieved source chunks">
        {chunks.map((chunk, idx) => (
          <li
            key={chunk.chunk_id}
            data-testid={`source-chunk-${idx + 1}`}
            aria-current={highlightedIndex === idx + 1 ? 'true' : undefined}
            className={`rounded-lg border p-3 text-sm motion-safe:transition-colors ${
              highlightedIndex === idx + 1
                ? 'border-blue-400 bg-blue-50'
                : 'border-gray-200 bg-white'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-gray-900 truncate">
                {chunk.section_heading || 'Untitled Section'}
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <span
                  className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${getMethodBadge(chunk.retrieval_method)}`}
                  aria-label={`Retrieval method: ${chunk.retrieval_method}`}
                >
                  {chunk.retrieval_method}
                </span>
                <span
                  className="text-xs text-gray-500"
                  aria-label={`Relevance score: ${(chunk.score * 100).toFixed(0)}%`}
                >
                  {(chunk.score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <p className="text-gray-700 whitespace-pre-wrap break-words leading-relaxed">
              {chunk.text}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
};

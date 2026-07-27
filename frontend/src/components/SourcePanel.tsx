import { type FC, useEffect, useRef } from 'react';
import type { SourceChunk } from '@/types/api';

interface SourcePanelProps {
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
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

function getScoreColorClass(score: number): string {
  if (score >= 0.7) return 'text-confidence-high';
  if (score >= 0.4) return 'text-confidence-medium';
  return 'text-confidence-low';
}

export const SourcePanel: FC<SourcePanelProps> = ({ chunks, highlightedIndex }) => {
  const highlightedRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (highlightedIndex !== undefined && highlightedRef.current) {
      highlightedRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedIndex]);

  if (chunks.length === 0) return null;

  return (
    <aside
      aria-label="Source panel"
      data-testid="source-panel"
      className="rounded-lg border border-gray-200 p-4 space-y-3 overflow-y-auto max-h-[500px]"
    >
      <h3 className="text-sm font-semibold text-gray-900">Sources</h3>
      <ol className="space-y-2" aria-label="Retrieved source chunks">
        {chunks.map((chunk, idx) => {
          const citationIndex = idx + 1;
          const isHighlighted = highlightedIndex === citationIndex;

          return (
            <li
              key={chunk.chunk_id}
              ref={isHighlighted ? highlightedRef : undefined}
              data-testid={`source-chunk-${citationIndex}`}
              aria-current={isHighlighted ? 'true' : undefined}
              className={`rounded-lg border p-3 text-sm motion-safe:transition-all motion-safe:duration-200 ${
                isHighlighted
                  ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-300 ring-offset-1'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span
                  className="font-medium text-gray-900 truncate"
                  data-testid={`source-heading-${citationIndex}`}
                >
                  {chunk.section_heading || 'Untitled Section'}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${getMethodBadge(chunk.retrieval_method)}`}
                    data-testid={`source-method-${citationIndex}`}
                    aria-label={`Retrieval method: ${chunk.retrieval_method}`}
                  >
                    {chunk.retrieval_method}
                  </span>
                  <span
                    className={`text-xs font-medium ${getScoreColorClass(chunk.score)}`}
                    data-testid={`source-score-${citationIndex}`}
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
          );
        })}
      </ol>
    </aside>
  );
};

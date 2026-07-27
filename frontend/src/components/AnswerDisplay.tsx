import { type FC } from 'react';
import type { AgentAskResponse } from '@/types/api';
import { ConfidenceScore } from '@/components/ConfidenceScore';
import { ConfidenceIndicator } from '@/components/ConfidenceIndicator';
import { CitationList } from '@/components/CitationList';
import { SourcePanel } from '@/components/SourcePanel';
import { FallbackDisplay } from '@/components/FallbackDisplay';
import { AnswerText } from '@/components/AnswerText';

interface AnswerDisplayProps {
  response: AgentAskResponse;
  onCitationClick?: (index: number) => void;
  highlightedChunk?: number;
}

export const AnswerDisplay: FC<AnswerDisplayProps> = ({
  response,
  onCitationClick,
  highlightedChunk,
}) => {
  return (
    <article className="space-y-4" aria-label="Answer" data-testid="answer-display">
      {response.is_fallback && response.fallback_info && (
        <FallbackDisplay fallbackInfo={response.fallback_info} />
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="prose prose-sm max-w-none flex-1">
          <AnswerText text={response.answer} onCitationClick={onCitationClick} />
        </div>
        <ConfidenceIndicator score={response.confidence_scores.composite} />
      </div>

      <ConfidenceScore scores={response.confidence_scores} />

      <CitationList
        citations={response.citations}
        onCitationClick={onCitationClick}
      />

      <SourcePanel
        chunks={response.source_chunks}
        highlightedIndex={highlightedChunk}
      />
    </article>
  );
};

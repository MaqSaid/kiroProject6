import { type FC } from 'react';
import type { ConfidenceScores } from '@/types/api';

interface ConfidenceScoreProps {
  scores: ConfidenceScores;
}

function getColorClass(score: number): string {
  if (score >= 0.7) return 'text-confidence-high bg-green-50';
  if (score >= 0.4) return 'text-confidence-medium bg-amber-50';
  return 'text-confidence-low bg-red-50';
}

function getBarColorClass(score: number): string {
  if (score >= 0.7) return 'bg-confidence-high';
  if (score >= 0.4) return 'bg-confidence-medium';
  return 'bg-confidence-low';
}

function getLabel(score: number): string {
  if (score >= 0.7) return 'High';
  if (score >= 0.4) return 'Medium';
  return 'Low';
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const percentage = Math.round(score * 100);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-600 w-32 shrink-0">{label}</span>
      <div
        className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${percentage}%`}
      >
        <div
          className={`h-full rounded-full motion-safe:transition-all motion-safe:duration-300 ${getBarColorClass(score)}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className={`text-xs font-medium w-10 text-right ${getColorClass(score)} px-1 rounded`}>
        {percentage}%
      </span>
    </div>
  );
}

export const ConfidenceScore: FC<ConfidenceScoreProps> = ({ scores }) => {
  const compositeLabel = getLabel(scores.composite);

  return (
    <section
      aria-label="Confidence scores"
      data-testid="confidence-scores"
      className="rounded-lg border border-gray-200 p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">Confidence</h3>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${getColorClass(scores.composite)}`}
          aria-label={`Overall confidence: ${compositeLabel}`}
        >
          {compositeLabel}
        </span>
      </div>
      <div className="space-y-2">
        <ScoreBar label="Retrieval" score={scores.retrieval_confidence} />
        <ScoreBar label="Citation Coverage" score={scores.citation_coverage} />
        <ScoreBar label="Completeness" score={scores.answer_completeness} />
        <ScoreBar label="Composite" score={scores.composite} />
      </div>
    </section>
  );
};

import { type FC } from 'react';

interface ConfidenceIndicatorProps {
  score: number;
}

/**
 * Returns Tailwind classes using the confidence theme tokens.
 * Green for score >= 0.7, amber for score >= 0.4, red for score < 0.4.
 */
export function getConfidenceLevel(score: number): {
  colorClass: string;
  bgClass: string;
  label: string;
} {
  if (score >= 0.7) {
    return {
      colorClass: 'text-confidence-high',
      bgClass: 'bg-confidence-high',
      label: 'High confidence',
    };
  }
  if (score >= 0.4) {
    return {
      colorClass: 'text-confidence-medium',
      bgClass: 'bg-confidence-medium',
      label: 'Medium confidence',
    };
  }
  return {
    colorClass: 'text-confidence-low',
    bgClass: 'bg-confidence-low',
    label: 'Low confidence',
  };
}

export const ConfidenceIndicator: FC<ConfidenceIndicatorProps> = ({ score }) => {
  const { colorClass, bgClass, label } = getConfidenceLevel(score);
  const percentage = Math.round(score * 100);

  return (
    <div
      data-testid="confidence-indicator"
      aria-label={`${label}: ${percentage}%`}
      className="inline-flex items-center gap-2"
    >
      <span
        className={`inline-block h-3 w-3 rounded-full ${bgClass}`}
        aria-hidden="true"
      />
      <span className={`text-sm font-medium ${colorClass}`}>
        {percentage}%
      </span>
      <span className="sr-only">{label}</span>
    </div>
  );
};

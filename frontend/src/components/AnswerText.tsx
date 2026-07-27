import { type FC } from 'react';

interface AnswerTextProps {
  text: string;
  onCitationClick?: (index: number) => void;
}

/**
 * Renders answer text with inline citation markers [1], [2], etc.
 * Citation markers are rendered as clickable buttons that trigger navigation
 * to the corresponding source chunk in the source panel.
 */
export const AnswerText: FC<AnswerTextProps> = ({ text, onCitationClick }) => {
  const parts = parseCitations(text);

  return (
    <p className="whitespace-pre-wrap leading-relaxed text-gray-900" data-testid="answer-text">
      {parts.map((part, idx) => {
        if (part.type === 'text') {
          return <span key={idx}>{part.value}</span>;
        }
        return (
          <button
            key={idx}
            type="button"
            onClick={() => onCitationClick?.(part.citationIndex)}
            className="relative inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-1 py-0.5 text-sm font-medium text-blue-700 bg-blue-50 rounded hover:bg-blue-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 motion-safe:transition-colors align-middle mx-0.5"
            aria-label={`Citation ${part.citationIndex}, go to source`}
            data-testid={`citation-marker-${part.citationIndex}`}
          >
            [{part.citationIndex}]
          </button>
        );
      })}
    </p>
  );
};

interface TextPart {
  type: 'text';
  value: string;
}

interface CitationPart {
  type: 'citation';
  citationIndex: number;
}

type AnswerPart = TextPart | CitationPart;

/**
 * Parses answer text to extract citation markers like [1], [2], [12], etc.
 */
export function parseCitations(text: string): AnswerPart[] {
  const regex = /\[(\d+)\]/g;
  const parts: AnswerPart[] = [];
  let lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, match.index) });
    }
    parts.push({ type: 'citation', citationIndex: parseInt(match[1] ?? '0', 10) });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return parts;
}

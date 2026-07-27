import { type FC, useRef, useEffect } from 'react';
import { AnswerDisplay } from '@/components/AnswerDisplay';
import type { Message } from '@/types/api';

interface MessageBubbleProps {
  message: Message;
  onCitationClick?: (index: number) => void;
  highlightedChunk?: number;
}

export const MessageBubble: FC<MessageBubbleProps> = ({
  message,
  onCitationClick,
  highlightedChunk,
}) => {
  const articleRef = useRef<HTMLElement>(null);

  // Focus management: move focus to new assistant messages when they arrive
  useEffect(() => {
    if (message.role === 'assistant' && !message.pending && articleRef.current) {
      articleRef.current.focus();
    }
  }, [message.role, message.pending]);

  return (
    <article
      ref={articleRef}
      tabIndex={-1}
      aria-label={message.role === 'user' ? 'Your message' : 'Assistant response'}
      className={`rounded-lg p-4 outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
        message.role === 'user'
          ? 'bg-blue-50 border border-blue-100 ml-8'
          : 'bg-white border border-gray-200 mr-8'
      }`}
    >
      <p className="text-xs font-medium text-gray-500 mb-2 uppercase" aria-hidden="true">
        {message.role === 'user' ? 'You' : 'Assistant'}
      </p>

      {message.role === 'user' && (
        <p className="text-sm text-gray-900">{message.content}</p>
      )}

      {message.role === 'assistant' && message.pending && (
        <div aria-busy="true" role="status" className="flex items-center gap-2 text-sm text-gray-500">
          <svg
            className="animate-spin h-4 w-4 motion-reduce:hidden"
            aria-hidden="true"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>Thinking...</span>
        </div>
      )}

      {message.role === 'assistant' && !message.pending && message.response && (
        <AnswerDisplay
          response={message.response}
          onCitationClick={onCitationClick}
          highlightedChunk={highlightedChunk}
        />
      )}
    </article>
  );
};

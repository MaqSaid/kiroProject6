import { type FC } from 'react';
import { MessageBubble } from '@/components/MessageBubble';
import type { Message } from '@/types/api';

interface ConversationHistoryProps {
  messages: Message[];
  onCitationClick?: (index: number) => void;
  highlightedChunk?: number;
}

export const ConversationHistory: FC<ConversationHistoryProps> = ({
  messages,
  onCitationClick,
  highlightedChunk,
}) => {
  return (
    <div
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      aria-label="Conversation history"
      className="flex-1 space-y-6 overflow-y-auto"
    >
      {messages.length === 0 && (
        <div className="text-center py-16">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Ask a question
          </h2>
          <p className="text-sm text-gray-500">
            Query your ingested documents using natural language.
          </p>
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onCitationClick={onCitationClick}
          highlightedChunk={highlightedChunk}
        />
      ))}
    </div>
  );
};

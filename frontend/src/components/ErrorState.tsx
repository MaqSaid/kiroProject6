import { type FC } from 'react';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export const ErrorState: FC<ErrorStateProps> = ({ message, onRetry }) => {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm"
    >
      <div className="flex items-start gap-3">
        <svg
          className="h-5 w-5 text-red-600 shrink-0 mt-0.5"
          aria-hidden="true"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
          />
        </svg>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-red-800">Something went wrong</p>
          <p className="mt-1 text-red-700">{message}</p>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-3 py-2 text-sm font-medium text-red-700 bg-red-100 rounded-md hover:bg-red-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 motion-safe:transition-colors"
            aria-label="Retry the failed request"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
};

import { type FC, useCallback, useRef, useState } from 'react';
import { useIngest } from '@/hooks/useIngest';

const ALLOWED_EXTENSIONS = ['.txt', '.md', '.html', '.pdf'];
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB

function getFileExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf('.');
  if (dotIndex === -1) return '';
  return filename.slice(dotIndex).toLowerCase();
}

function validateFile(file: File): string | null {
  const ext = getFileExtension(file.name);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Invalid file type "${ext || '(none)'}". Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File exceeds maximum size of 50 MB (${(file.size / (1024 * 1024)).toFixed(1)} MB).`;
  }
  return null;
}

export const DocumentUpload: FC = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { mutate, isPending, isError, error, isSuccess, data, reset } = useIngest();

  const handleUpload = useCallback(
    (file: File) => {
      setValidationError(null);
      reset();

      const validationMessage = validateFile(file);
      if (validationMessage) {
        setValidationError(validationMessage);
        return;
      }

      setSelectedFile(file);
      mutate(file);
    },
    [mutate, reset],
  );

  const handleRetry = useCallback(() => {
    if (selectedFile) {
      reset();
      setValidationError(null);
      mutate(selectedFile);
    }
  }, [selectedFile, mutate, reset]);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file) {
      handleUpload(file);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
  }

  return (
    <section aria-label="Upload document" className="space-y-3">
      <h2 className="text-lg font-semibold text-gray-900">Upload Document</h2>

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative flex flex-col items-center justify-center min-h-[160px] rounded-lg border-2 border-dashed p-6 motion-safe:transition-colors ${
          dragActive
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 bg-gray-50 hover:border-gray-400'
        }`}
      >
        <svg
          className="h-10 w-10 text-gray-400 mb-3"
          aria-hidden="true"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm text-gray-600 mb-2">
          Drag and drop a file here, or
        </p>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isPending}
          aria-busy={isPending}
          className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-4 py-2 text-sm font-medium text-blue-700 bg-blue-50 rounded-md hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-safe:transition-colors"
        >
          {isPending ? 'Uploading...' : 'Browse files'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          onChange={(e) => {
            handleFiles(e.target.files);
            // Reset input value so the same file can be re-selected
            e.target.value = '';
          }}
          accept=".txt,.md,.html,.pdf"
          className="sr-only"
          aria-label="Select file to upload"
          aria-describedby={validationError ? 'upload-validation-error' : undefined}
        />
        <p className="text-xs text-gray-500 mt-3">
          Accepted formats: .txt, .md, .html, .pdf (max 50 MB)
        </p>
      </div>

      {validationError && (
        <div
          id="upload-validation-error"
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm"
        >
          <p className="text-red-800">{validationError}</p>
        </div>
      )}

      {isPending && (
        <div role="status" aria-live="polite" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm">
          <p className="text-blue-800">
            Uploading{selectedFile ? ` "${selectedFile.name}"` : ''}… This may take up to 60 seconds.
          </p>
        </div>
      )}

      {isSuccess && data && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm">
          <p className="text-green-800">
            <strong>{selectedFile?.name ?? 'Document'}</strong> uploaded successfully — {data.chunks_produced} chunks created.
          </p>
        </div>
      )}

      {isError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <p className="text-red-800">
              Upload failed: {error?.message ?? 'Network error. Please try again.'}
            </p>
            {selectedFile && (
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-3 py-2 text-sm font-medium text-red-700 bg-red-100 rounded-md hover:bg-red-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 motion-safe:transition-colors shrink-0"
                aria-label="Retry upload"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

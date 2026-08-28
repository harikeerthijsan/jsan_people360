'use client';

import { FileText, Image as ImageIcon, Upload, X } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * A drag-and-drop file picker with an upload progress bar.
 *
 * Built as a labelled input rather than a bare div with a click handler: a real
 * `<input type="file">` is what makes the control reachable by keyboard and
 * announced correctly, and the drop zone is layered on top of it rather than
 * replacing it.
 *
 * Validation is injected. This component knows how to accept a file and show a
 * problem; what counts as a problem belongs to whoever is using it.
 */

export interface FileUploadProps {
  /** Called when a file is accepted. Null when the selection is cleared. */
  onSelect: (file: File | null) => void;
  /** Return a message to reject the file, or null to accept it. */
  validate?: (file: File) => { message: string } | null;
  /** Passed to the input's `accept`, e.g. `.pdf,.jpg`. */
  accept?: string;
  /** 0–100 while uploading; omit when idle. */
  progress?: number;
  isUploading?: boolean;
  disabled?: boolean;
  /** Describes what belongs here, e.g. "PDF, JPG or PNG, up to 10 MB". */
  hint?: string;
  label?: string;
  className?: string;
}

function iconFor(file: File): React.ReactNode {
  return file.type.startsWith('image/') ? (
    <ImageIcon className="size-5" aria-hidden="true" />
  ) : (
    <FileText className="size-5" aria-hidden="true" />
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileUpload({
  onSelect,
  validate,
  accept,
  progress,
  isUploading = false,
  disabled = false,
  hint,
  label = 'Choose a file',
  className,
}: FileUploadProps): React.JSX.Element {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [selected, setSelected] = React.useState<File | null>(null);
  const [rejection, setRejection] = React.useState<string | null>(null);
  const [isDragging, setIsDragging] = React.useState(false);

  // A drag entering a child element fires dragleave on the parent, so a plain
  // boolean flickers. Counting enter and leave keeps the state honest.
  const dragDepth = React.useRef(0);

  const accept_ = React.useCallback(
    (file: File | undefined) => {
      if (!file) return;

      const problem = validate?.(file) ?? null;
      if (problem) {
        setRejection(problem.message);
        setSelected(null);
        onSelect(null);
        return;
      }

      setRejection(null);
      setSelected(file);
      onSelect(file);
    },
    [onSelect, validate],
  );

  const clear = React.useCallback(() => {
    setSelected(null);
    setRejection(null);
    onSelect(null);
    // Without this the same file cannot be re-picked: the input's value is
    // unchanged, so no change event fires.
    if (inputRef.current) inputRef.current.value = '';
  }, [onSelect]);

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);
    if (disabled || isUploading) return;
    accept_(event.dataTransfer.files[0]);
  };

  const showProgress = isUploading && typeof progress === 'number';

  return (
    <div className={cn('space-y-2', className)}>
      <div
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          if (!disabled && !isUploading) setIsDragging(true);
        }}
        onDragLeave={() => {
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) setIsDragging(false);
        }}
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDrop={onDrop}
        className={cn(
          'relative rounded-md border-2 border-dashed transition-colors',
          isDragging ? 'border-primary bg-primary-subtle' : 'border-border',
          disabled && 'opacity-60',
        )}
      >
        {selected === null ? (
          <label
            className={cn(
              'flex cursor-pointer flex-col items-center gap-2 px-6 py-8 text-center',
              disabled && 'cursor-not-allowed',
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept={accept}
              disabled={disabled || isUploading}
              className="sr-only"
              onChange={(event) => {
                accept_(event.target.files?.[0]);
              }}
            />
            <Upload className="text-muted-foreground size-6" aria-hidden="true" />
            <span className="text-sm font-medium">
              {label}
              <span className="text-muted-foreground font-normal"> or drag it here</span>
            </span>
            {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
          </label>
        ) : (
          <div className="flex items-center gap-3 p-4">
            <span className="text-muted-foreground shrink-0">{iconFor(selected)}</span>

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{selected.name}</p>
              <p className="text-muted-foreground text-xs">{formatSize(selected.size)}</p>

              {showProgress ? (
                <div className="mt-2 space-y-1">
                  <div
                    className="bg-muted h-1.5 overflow-hidden rounded-full"
                    role="progressbar"
                    aria-valuenow={progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Upload progress"
                  >
                    <div
                      className="bg-primary h-full rounded-full transition-[width] duration-150"
                      style={{ width: `${String(progress)}%` }}
                    />
                  </div>
                  <p className="text-muted-foreground text-xs tabular-nums">
                    {progress === 100 ? 'Finishing…' : `Uploading… ${String(progress)}%`}
                  </p>
                </div>
              ) : null}
            </div>

            {isUploading ? null : (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={clear}
                aria-label={`Remove ${selected.name}`}
                disabled={disabled}
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            )}
          </div>
        )}
      </div>

      {rejection ? (
        // role="alert" so the rejection is announced: a drag-and-drop user may
        // not be looking at this corner of the screen.
        <p role="alert" className="text-destructive text-sm">
          {rejection}
        </p>
      ) : null}
    </div>
  );
}

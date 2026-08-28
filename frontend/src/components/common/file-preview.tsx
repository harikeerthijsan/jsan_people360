'use client';

import { Download, FileQuestion } from 'lucide-react';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { AppError } from '@/lib/errors';
import { cn } from '@/lib/utils';

/**
 * Viewers for the formats the vault accepts, and a modal that hosts them.
 *
 * Both viewers take an object URL rather than a path: the file endpoints
 * require a bearer token, so the bytes are fetched by the application and
 * handed here already in memory. Pointing an `<img>` at the API URL would send
 * an unauthenticated request.
 */

interface ViewerProps {
  /** Object URL for the already-fetched bytes. */
  url: string;
  filename: string;
  className?: string;
}

export function ImageViewer({ url, filename, className }: ViewerProps): React.JSX.Element {
  return (
    <div className={cn('bg-muted/40 flex justify-center rounded-md p-4', className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- an object URL
          cannot be optimised by next/image, which needs a real remote URL. */}
      <img src={url} alt={filename} className="max-h-[70vh] max-w-full rounded object-contain" />
    </div>
  );
}

export function PdfViewer({ url, filename, className }: ViewerProps): React.JSX.Element {
  return (
    // An <object> rather than an <iframe>: it degrades to its children when the
    // browser has no PDF plugin, which gives a real fallback instead of a blank
    // rectangle.
    <object
      data={url}
      type="application/pdf"
      aria-label={filename}
      className={cn('bg-muted/40 h-[70vh] w-full rounded-md', className)}
    >
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <FileQuestion className="text-muted-foreground size-8" aria-hidden="true" />
        <p className="text-sm">Your browser cannot display PDFs inline.</p>
        <Button asChild variant="outline" size="sm">
          <a href={url} download={filename}>
            <Download aria-hidden="true" />
            Download to view
          </a>
        </Button>
      </div>
    </object>
  );
}

interface FilePreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Shown under the title — the version, or when it was uploaded. */
  description?: string;
  filename: string;
  contentType: string;
  /** Object URL, or null while it is being fetched. */
  url: string | null;
  isLoading?: boolean;
  error?: AppError | null;
  onDownload?: () => void;
}

/** The modal that shows a document without leaving the page. */
export function FilePreviewModal({
  open,
  onOpenChange,
  title,
  description,
  filename,
  contentType,
  url,
  isLoading = false,
  error = null,
  onDownload,
}: FilePreviewModalProps): React.JSX.Element {
  const isImage = contentType.startsWith('image/');
  const isPdf = contentType === 'application/pdf';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>

        {error ? (
          <ErrorState error={error} compact />
        ) : isLoading || url === null ? (
          <LoadingState message="Loading preview" />
        ) : isImage ? (
          <ImageViewer url={url} filename={filename} />
        ) : isPdf ? (
          <PdfViewer url={url} filename={filename} />
        ) : (
          <div className="flex flex-col items-center gap-3 p-8 text-center">
            <FileQuestion className="text-muted-foreground size-8" aria-hidden="true" />
            <p className="text-sm">This file type cannot be previewed.</p>
          </div>
        )}

        {onDownload ? (
          <div className="flex justify-end">
            <Button variant="outline" onClick={onDownload}>
              <Download aria-hidden="true" />
              Download
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

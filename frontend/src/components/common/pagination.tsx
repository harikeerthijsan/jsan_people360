'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface PageMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

interface PaginationProps {
  meta: PageMeta;
  onPageChange: (page: number) => void;
  /** Noun for the range summary, e.g. "teams". */
  itemLabel?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Page controls with a plain-language range summary.
 *
 * The summary matters as much as the buttons: "Showing 21–40 of 57" tells the
 * user where they are, which bare arrows do not.
 */
export function Pagination({
  meta,
  onPageChange,
  itemLabel = 'records',
  className,
  disabled = false,
}: PaginationProps): React.JSX.Element | null {
  if (meta.total_items === 0) {
    return null;
  }

  const firstItem = (meta.page - 1) * meta.page_size + 1;
  const lastItem = Math.min(meta.page * meta.page_size, meta.total_items);

  return (
    <div className={cn('flex flex-col items-center justify-between gap-3 px-1 pt-3 sm:flex-row', className)}>
      <p className="text-muted-foreground text-sm" aria-live="polite">
        Showing <span className="text-foreground font-medium">{firstItem}</span>–
        <span className="text-foreground font-medium">{lastItem}</span> of{' '}
        <span className="text-foreground font-medium">{meta.total_items}</span> {itemLabel}
      </p>

      <nav className="flex items-center gap-2" aria-label="Pagination">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            onPageChange(meta.page - 1);
          }}
          disabled={disabled || !meta.has_previous}
        >
          <ChevronLeft aria-hidden="true" />
          Previous
        </Button>

        <span className="text-muted-foreground px-2 text-sm tabular-nums">
          Page {meta.page} of {Math.max(meta.total_pages, 1)}
        </span>

        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            onPageChange(meta.page + 1);
          }}
          disabled={disabled || !meta.has_next}
        >
          Next
          <ChevronRight aria-hidden="true" />
        </Button>
      </nav>
    </div>
  );
}

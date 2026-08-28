import { Loader2 } from 'lucide-react';
import * as React from 'react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface SpinnerProps {
  className?: string;
  label?: string;
}

/** A centred spinner with an accessible label. */
export function Spinner({ className, label = 'Loading' }: SpinnerProps): React.JSX.Element {
  return (
    <span role="status" className={cn('text-muted-foreground inline-flex items-center gap-2', className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

interface LoadingStateProps {
  /** Shown beneath the spinner; keep it specific ("Loading employees…"). */
  message?: string;
  className?: string;
}

/**
 * The default full-region loading indicator.
 *
 * Prefer a skeleton when the shape of the incoming content is known -- it
 * avoids the layout shift a spinner causes when real content arrives.
 */
export function LoadingState({ message = 'Loading…', className }: LoadingStateProps): React.JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex min-h-48 flex-col items-center justify-center gap-3 p-8 text-center', className)}
    >
      <Loader2 className="text-primary size-6 animate-spin" aria-hidden="true" />
      <p className="text-muted-foreground text-sm">{message}</p>
    </div>
  );
}

/** Skeleton matching the shape of a stat card row. */
export function StatCardSkeleton(): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent className="space-y-2">
        <Skeleton className="h-7 w-16" />
        <Skeleton className="h-3 w-32" />
      </CardContent>
    </Card>
  );
}

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

/** Skeleton matching the shape of a data table. */
export function TableSkeleton({ rows = 5, columns = 4 }: TableSkeletonProps): React.JSX.Element {
  return (
    <div className="bg-card space-y-3 rounded-2xl p-4 shadow-sm" role="status" aria-live="polite">
      <span className="sr-only">Loading table data</span>
      <div className="border-border/70 flex gap-4 border-b pb-3">
        {Array.from({ length: columns }, (_, index) => (
          <Skeleton key={`head-${String(index)}`} className="h-4 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={`row-${String(rowIndex)}`} className="flex gap-4 py-1.5">
          {Array.from({ length: columns }, (_, columnIndex) => (
            <Skeleton key={`cell-${String(rowIndex)}-${String(columnIndex)}`} className="h-5 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Skeleton for a form panel. */
export function FormSkeleton({ fields = 4 }: { fields?: number }): React.JSX.Element {
  return (
    <div className="space-y-5" role="status" aria-live="polite">
      <span className="sr-only">Loading form</span>
      {Array.from({ length: fields }, (_, index) => (
        <div key={`field-${String(index)}`} className="space-y-2">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
      <Skeleton className="h-9 w-32" />
    </div>
  );
}

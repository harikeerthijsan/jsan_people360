import type * as React from 'react';

import { StatCardSkeleton } from '@/components/common/loading-state';
import { Skeleton } from '@/components/ui/skeleton';

/** Skeleton mirroring the dashboard layout, so nothing shifts when data lands. */
export default function DashboardLoading(): React.JSX.Element {
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      <span className="sr-only">Loading dashboard</span>

      <div className="border-border space-y-2 border-b pb-5">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>

      <Skeleton className="h-20 w-full" />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <StatCardSkeleton key={`stat-${String(index)}`} />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="h-80 lg:col-span-2" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}

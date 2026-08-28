import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';

/** Fallback shown while a route segment streams in. */
export default function Loading(): React.JSX.Element {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <LoadingState message="Loading…" />
    </div>
  );
}

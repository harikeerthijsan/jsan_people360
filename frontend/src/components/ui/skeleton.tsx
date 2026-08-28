import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * A shimmering placeholder used while content loads.
 *
 * `aria-hidden` keeps screen readers from announcing decorative boxes -- the
 * surrounding container is responsible for announcing the busy state.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>): React.JSX.Element {
  return <div aria-hidden="true" className={cn('bg-muted animate-pulse rounded-md', className)} {...props} />;
}

export { Skeleton };

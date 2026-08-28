import Link from 'next/link';
import * as React from 'react';

import { routes, siteConfig } from '@/config/site';
import { cn } from '@/lib/utils';

interface BrandProps {
  /** Hide the wordmark, leaving only the mark (used by the collapsed sidebar). */
  compact?: boolean;
  /** Render for a dark surface such as the blue navigation rail. */
  inverted?: boolean;
  className?: string;
}

/** The product lockup: mark plus wordmark, linking home. */
export function Brand({ compact = false, inverted = false, className }: BrandProps): React.JSX.Element {
  return (
    <Link
      href={routes.dashboard}
      className={cn('flex items-center gap-2.5 rounded-md transition-opacity hover:opacity-90', className)}
    >
      <span
        className={cn(
          'flex size-8 shrink-0 items-center justify-center rounded-md text-sm font-bold',
          inverted ? 'text-primary bg-white' : 'bg-primary text-primary-foreground',
        )}
        aria-hidden="true"
      >
        J
      </span>

      {!compact ? (
        <span className="flex min-w-0 flex-col leading-tight">
          <span
            className={cn(
              'truncate text-sm font-semibold tracking-tight',
              inverted ? 'text-sidebar-foreground' : 'text-foreground',
            )}
          >
            {siteConfig.name}
          </span>
          <span
            className={cn('truncate text-[11px]', inverted ? 'text-sidebar-muted' : 'text-muted-foreground')}
          >
            {siteConfig.company}
          </span>
        </span>
      ) : null}

      <span className="sr-only">{siteConfig.name} home</span>
    </Link>
  );
}

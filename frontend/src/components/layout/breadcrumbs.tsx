'use client';

import { ChevronRight, Home } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { routes } from '@/config/site';
import { useBreadcrumbs } from '@/hooks/use-breadcrumbs';
import { cn } from '@/lib/utils';

/**
 * The breadcrumb trail for the current route.
 *
 * Rendered as an ordered list inside a labelled `nav`, with `aria-current` on
 * the final crumb -- the structure assistive technology expects.
 */
export function Breadcrumbs({ className }: { className?: string }): React.JSX.Element | null {
  const crumbs = useBreadcrumbs();

  // A single crumb is just the page title, which the page header already shows.
  if (crumbs.length <= 1) {
    return null;
  }

  return (
    <nav aria-label="Breadcrumb" className={cn('min-w-0', className)}>
      <ol className="flex items-center gap-1.5 text-sm">
        <li className="flex items-center">
          <Link
            href={routes.dashboard}
            className="text-muted-foreground hover:text-foreground flex items-center transition-colors"
          >
            <Home className="size-3.5" aria-hidden="true" />
            <span className="sr-only">Dashboard</span>
          </Link>
        </li>

        {crumbs.map((crumb) => (
          <li key={crumb.href} className="flex min-w-0 items-center gap-1.5">
            <ChevronRight className="text-muted-foreground/60 size-3.5 shrink-0" aria-hidden="true" />

            {crumb.isCurrent ? (
              <span aria-current="page" className="text-foreground truncate font-medium">
                {crumb.label}
              </span>
            ) : (
              <Link
                href={crumb.href}
                className="text-muted-foreground hover:text-foreground truncate transition-colors"
              >
                {crumb.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

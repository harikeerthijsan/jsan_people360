'use client';

import { usePathname } from 'next/navigation';
import * as React from 'react';

import { navigationIndex } from '@/config/navigation';
import { routes } from '@/config/site';
import { humanizeSegment } from '@/lib/utils';

export interface Breadcrumb {
  label: string;
  href: string;
  /** True for the final crumb, which is rendered as text rather than a link. */
  isCurrent: boolean;
}

const UUID_SEGMENT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Derive breadcrumbs from the current route.
 *
 * Labels come from the navigation config when the path is a known module, so
 * the sidebar and the breadcrumb trail can never drift apart. Unknown segments
 * (ids, sub-pages) fall back to a humanised version of the segment itself.
 */
export function useBreadcrumbs(): Breadcrumb[] {
  const pathname = usePathname();

  return React.useMemo(() => {
    const segments = pathname.split('/').filter(Boolean);

    if (segments.length === 0) {
      return [{ label: 'Dashboard', href: routes.dashboard, isCurrent: true }];
    }

    const crumbs: Breadcrumb[] = [];
    let href = '';

    for (const [index, segment] of segments.entries()) {
      href += `/${segment}`;
      const known = navigationIndex.get(href);

      // A record id is not a label. Humanising it produces something like
      // "50fe82ac 591c 4afc 9390 D244f8665cba", which is worse than useless in
      // a breadcrumb, so identifier segments get a generic label instead.
      const label =
        known?.breadcrumbLabel ??
        known?.label ??
        (UUID_SEGMENT.test(segment) ? 'Details' : humanizeSegment(segment));

      crumbs.push({ label, href, isCurrent: index === segments.length - 1 });
    }

    return crumbs;
  }, [pathname]);
}

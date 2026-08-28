'use client';

import { usePathname } from 'next/navigation';
import * as React from 'react';

/**
 * Fades and lifts page content in on every route change.
 *
 * Keyed on the pathname so the animation re-runs when the page changes and
 * not when the page merely re-renders. The motion itself is a CSS class, so
 * `prefers-reduced-motion` switches it off in one place.
 */
export function PageTransition({ children }: { children: React.ReactNode }): React.JSX.Element {
  const pathname = usePathname();
  return (
    <div key={pathname} className="animate-rise">
      {children}
    </div>
  );
}

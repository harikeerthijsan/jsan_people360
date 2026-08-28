'use client';

import * as React from 'react';

/**
 * Track a CSS media query from React.
 *
 * `useSyncExternalStore` is used rather than `useState` + `useEffect` so the
 * value is correct on the very first client render and cannot tear during
 * concurrent rendering. The server snapshot is `false`, matching the
 * mobile-first default.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = React.useCallback(
    (onStoreChange: () => void) => {
      const mediaQueryList = window.matchMedia(query);
      mediaQueryList.addEventListener('change', onStoreChange);
      return () => {
        mediaQueryList.removeEventListener('change', onStoreChange);
      };
    },
    [query],
  );

  const getSnapshot = React.useCallback(() => window.matchMedia(query).matches, [query]);
  const getServerSnapshot = React.useCallback(() => false, []);

  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Matches the Tailwind `lg` breakpoint, where the sidebar becomes permanent. */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 1024px)');
}

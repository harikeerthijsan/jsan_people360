'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import * as React from 'react';

import { createQueryClient } from '@/lib/query-client';

/**
 * Provides the TanStack Query cache.
 *
 * The client is created in lazy state rather than at module scope: a
 * module-level singleton would be shared between users during server rendering
 * and could leak one user's cached data into another's response.
 */
export function QueryProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [queryClient] = React.useState(createQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

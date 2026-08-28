'use client';

import * as React from 'react';

import { AuthProvider } from '@/components/providers/auth-provider';
import { QueryProvider } from '@/components/providers/query-provider';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';

/**
 * Single composition point for every client-side provider.
 *
 * Order matters: `AuthProvider` performs network calls, so it must sit inside
 * `QueryProvider`.
 */
export function AppProviders({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <QueryProvider>
      <AuthProvider>
        <TooltipProvider delayDuration={300}>
          {children}
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </QueryProvider>
  );
}

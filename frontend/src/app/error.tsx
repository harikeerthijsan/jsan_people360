'use client';

import { AlertTriangle, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { isProduction } from '@/lib/env';

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Route-level error boundary.
 *
 * The raw message is shown only outside production; in production the user sees
 * neutral copy plus the `digest`, which support can correlate with the server
 * log without exposing internals.
 */
export default function ErrorPage({ error, reset }: ErrorPageProps): React.JSX.Element {
  React.useEffect(() => {
    // Replace with the real telemetry sink when observability is wired up.
    console.error('Unhandled route error:', error);
  }, [error]);

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-16">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="bg-destructive-subtle mx-auto flex size-14 items-center justify-center rounded-full">
          <AlertTriangle className="text-destructive size-6" aria-hidden="true" />
        </div>

        <div className="space-y-2">
          <p className="text-destructive text-sm font-semibold tracking-wider uppercase">Error 500</p>
          <h1 className="text-foreground text-2xl font-semibold tracking-tight">Something went wrong</h1>
          <p className="text-muted-foreground text-sm">
            An unexpected error interrupted this page. Try again, and contact your administrator if the
            problem continues.
          </p>
        </div>

        {!isProduction && error.message ? (
          <pre className="bg-muted text-muted-foreground max-h-40 overflow-auto rounded-md p-3 text-left text-xs">
            {error.message}
          </pre>
        ) : null}

        {error.digest ? (
          <p className="text-muted-foreground text-xs">
            Reference: <code className="font-mono">{error.digest}</code>
          </p>
        ) : null}

        <div className="flex flex-col justify-center gap-2 sm:flex-row">
          <Button onClick={reset}>
            <RefreshCw aria-hidden="true" />
            Try again
          </Button>
          <Button variant="outline" asChild>
            <Link href={routes.dashboard}>Back to dashboard</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}

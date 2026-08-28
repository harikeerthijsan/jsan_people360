import { ArrowLeft, FileQuestion } from 'lucide-react';
import Link from 'next/link';
import type * as React from 'react';

import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';

/** Rendered for any unmatched route. */
export default function NotFound(): React.JSX.Element {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-16">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="bg-primary-subtle mx-auto flex size-14 items-center justify-center rounded-full">
          <FileQuestion className="text-primary size-6" aria-hidden="true" />
        </div>

        <div className="space-y-2">
          <p className="text-primary text-sm font-semibold tracking-wider uppercase">Error 404</p>
          <h1 className="text-foreground text-2xl font-semibold tracking-tight">Page not found</h1>
          <p className="text-muted-foreground text-sm">
            The page you are looking for does not exist, has been moved, or you may not have access to it.
          </p>
        </div>

        <div className="flex flex-col justify-center gap-2 sm:flex-row">
          <Button asChild>
            <Link href={routes.dashboard}>
              <ArrowLeft aria-hidden="true" />
              Back to dashboard
            </Link>
          </Button>
        </div>
      </div>
    </main>
  );
}

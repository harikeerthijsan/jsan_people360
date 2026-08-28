'use client';

import { Toaster as SonnerToaster, toast } from 'sonner';
import type * as React from 'react';

/**
 * Application-wide toast host.
 *
 * Styling is bound to the design tokens rather than Sonner's defaults so
 * notifications match the rest of the product.
 */
function Toaster(props: React.ComponentProps<typeof SonnerToaster>): React.JSX.Element {
  return (
    <SonnerToaster
      position="top-right"
      closeButton
      richColors={false}
      toastOptions={{
        classNames: {
          toast:
            'group flex w-full items-center gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-lg',
          title: 'text-sm font-semibold',
          description: 'text-sm text-muted-foreground',
          actionButton: 'bg-primary text-primary-foreground rounded-md px-2.5 py-1 text-xs font-medium',
          cancelButton: 'bg-secondary text-secondary-foreground rounded-md px-2.5 py-1 text-xs font-medium',
          success: 'border-success/30 [&_[data-icon]]:text-success',
          error: 'border-destructive/30 [&_[data-icon]]:text-destructive',
          warning: 'border-warning/40 [&_[data-icon]]:text-warning',
          info: 'border-primary/30 [&_[data-icon]]:text-primary',
        },
      }}
      {...props}
    />
  );
}

export { Toaster, toast };

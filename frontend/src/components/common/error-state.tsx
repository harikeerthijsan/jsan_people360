'use client';

import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { type AppError, toAppError } from '@/lib/errors';
import { cn } from '@/lib/utils';

interface ErrorStateProps {
  /** The thrown value; it is normalised internally. */
  error: unknown;
  /** Overrides the message derived from `error`. */
  title?: string;
  onRetry?: () => void;
  className?: string;
  /** Compact variant for inline use inside a card or table. */
  compact?: boolean;
}

/**
 * The canonical error panel.
 *
 * The message shown always comes from {@link AppError}, which is populated from
 * the backend's user-facing `message` field. Stack traces and internal detail
 * never reach this component.
 */
export function ErrorState({
  error,
  title,
  onRetry,
  className,
  compact = false,
}: ErrorStateProps): React.JSX.Element {
  const appError: AppError = toAppError(error);
  const Icon = appError.isNetworkError ? WifiOff : AlertTriangle;

  const heading = title ?? (appError.isNetworkError ? 'Cannot reach the server' : 'Something went wrong');

  return (
    <div
      role="alert"
      className={cn(
        'border-destructive/20 bg-destructive-subtle flex flex-col items-center justify-center gap-3 rounded-lg border text-center',
        compact ? 'p-5' : 'min-h-56 p-10',
        className,
      )}
    >
      <div className="bg-background flex size-11 items-center justify-center rounded-full shadow-sm">
        <Icon className="text-destructive size-5" aria-hidden="true" />
      </div>

      <div className="space-y-1">
        <h3 className="text-foreground text-sm font-semibold">{heading}</h3>
        <p className="text-muted-foreground mx-auto max-w-md text-sm">{appError.message}</p>
      </div>

      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry} className="mt-1">
          <RefreshCw className="size-4" aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}

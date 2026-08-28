import { Inbox, type LucideIcon } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface EmptyStateAction {
  label: string;
  onClick: () => void;
  variant?: React.ComponentProps<typeof Button>['variant'];
}

interface EmptyStateProps {
  /** What is missing, e.g. "No employees yet". */
  title: string;
  /** Why it is missing and what the user can do about it. */
  description?: string;
  icon?: LucideIcon;
  /** The primary way out of the empty state. */
  action?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
  className?: string;
}

/**
 * The canonical "there is nothing here" panel.
 *
 * A good empty state explains the absence *and* offers the next step, which is
 * why `action` exists alongside `description`.
 */
export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  secondaryAction,
  className,
}: EmptyStateProps): React.JSX.Element {
  return (
    <div
      className={cn(
        'border-border bg-muted/30 flex min-h-56 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-10 text-center',
        className,
      )}
    >
      <div className="bg-background flex size-12 items-center justify-center rounded-full shadow-sm">
        <Icon className="text-muted-foreground size-5" aria-hidden="true" />
      </div>

      <div className="space-y-1">
        <h3 className="text-foreground text-sm font-semibold">{title}</h3>
        {description ? <p className="text-muted-foreground mx-auto max-w-sm text-sm">{description}</p> : null}
      </div>

      {(action ?? secondaryAction) ? (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          {action ? (
            <Button size="sm" variant={action.variant ?? 'default'} onClick={action.onClick}>
              {action.label}
            </Button>
          ) : null}
          {secondaryAction ? (
            <Button
              size="sm"
              variant={secondaryAction.variant ?? 'outline'}
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

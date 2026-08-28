import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import {
  DOCUMENT_STATUS_LABELS,
  EXPIRY_STATE_LABELS,
  type DocumentStatus,
  type ExpiryState,
} from '@/features/documents/types/document.types';
import { cn } from '@/lib/utils';

/**
 * A document's review status, and separately its expiry.
 *
 * Two badges rather than one, because they answer different questions: a
 * document can be approved *and* expired, and collapsing them would hide
 * whichever the reader needed.
 */

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

const STATUS_VARIANT: Record<DocumentStatus, BadgeVariant> = {
  uploaded: 'secondary',
  under_review: 'warning',
  approved: 'success',
  rejected: 'destructive',
  expired: 'destructive',
  archived: 'outline',
};

interface DocumentStatusBadgeProps {
  status: DocumentStatus;
  /** Archived takes precedence: a hidden document's review state is moot. */
  archived?: boolean;
  className?: string;
}

export function DocumentStatusBadge({
  status,
  archived = false,
  className,
}: DocumentStatusBadgeProps): React.JSX.Element {
  if (archived) {
    return (
      <Badge variant="outline" className={cn('border-dashed', className)}>
        Archived
      </Badge>
    );
  }

  return (
    <Badge variant={STATUS_VARIANT[status]} className={className}>
      {DOCUMENT_STATUS_LABELS[status]}
    </Badge>
  );
}

const EXPIRY_VARIANT: Record<ExpiryState, BadgeVariant> = {
  none: 'outline',
  valid: 'success',
  expiring_soon: 'warning',
  expired: 'destructive',
};

interface ExpiryBadgeProps {
  state: ExpiryState;
  /** Rendered after the label, e.g. the date itself. */
  detail?: string;
  className?: string;
}

/**
 * The expiry state.
 *
 * Renders nothing for a document that does not expire: a "No expiry" badge on
 * every résumé would be noise that makes the real warnings harder to spot.
 */
export function ExpiryBadge({ state, detail, className }: ExpiryBadgeProps): React.JSX.Element | null {
  if (state === 'none') return null;

  return (
    <Badge variant={EXPIRY_VARIANT[state]} className={className}>
      {EXPIRY_STATE_LABELS[state]}
      {detail ? <span className="font-normal opacity-80"> · {detail}</span> : null}
    </Badge>
  );
}

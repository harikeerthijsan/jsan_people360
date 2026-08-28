import { Archive, CheckCircle2, MinusCircle } from 'lucide-react';
import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

/** Business status of a master record, mirroring the backend enum. */
export type RecordStatus = 'active' | 'inactive';

interface StatusBadgeProps {
  status: RecordStatus;
  /** Archived records show as archived regardless of their business status. */
  archived?: boolean;
  className?: string;
}

const PRESETS = {
  archived: {
    label: 'Archived',
    variant: 'secondary',
    icon: Archive,
  },
  active: {
    label: 'Active',
    variant: 'success',
    icon: CheckCircle2,
  },
  inactive: {
    label: 'Inactive',
    variant: 'outline',
    icon: MinusCircle,
  },
} as const;

/**
 * Renders a record's state as a single badge.
 *
 * Archived and inactive are genuinely different: an inactive record is hidden
 * from new selections but still live, while an archived one has been soft
 * deleted. Collapsing them into one label would hide that from the user, so
 * archived deliberately takes precedence and is labelled distinctly.
 */
export function StatusBadge({ status, archived = false, className }: StatusBadgeProps): React.JSX.Element {
  const preset = archived ? PRESETS.archived : PRESETS[status];
  const Icon = preset.icon;

  return (
    <Badge variant={preset.variant} className={cn('gap-1', className)}>
      <Icon className="size-3" aria-hidden="true" />
      {preset.label}
    </Badge>
  );
}

import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { EMPLOYMENT_STATUS_LABELS, type EmploymentStatus } from '@/features/employees/types/employee.types';
import { cn } from '@/lib/utils';

/**
 * An employee's lifecycle status as one badge.
 *
 * Separate from `StatusBadge`, which renders the master-data active/inactive
 * pair. Six states with different meanings do not collapse into two, and
 * pretending they do is how "on notice" ends up looking identical to "resigned".
 */

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

/**
 * The variant per status. Notice period is a warning rather than a failure --
 * the person is still employed and still needs handling -- while resigned and
 * inactive are terminal and read as neutral rather than alarming.
 */
const STATUS_VARIANT: Record<EmploymentStatus, BadgeVariant> = {
  probation: 'warning',
  confirmed: 'success',
  active: 'success',
  notice_period: 'warning',
  resigned: 'secondary',
  inactive: 'secondary',
};

interface EmploymentStatusBadgeProps {
  status: EmploymentStatus;
  /** Archived takes precedence: a hidden record's lifecycle state is moot. */
  archived?: boolean;
  className?: string;
}

export function EmploymentStatusBadge({
  status,
  archived = false,
  className,
}: EmploymentStatusBadgeProps): React.JSX.Element {
  if (archived) {
    return (
      <Badge variant="outline" className={cn('border-dashed', className)}>
        Archived
      </Badge>
    );
  }

  return (
    <Badge variant={STATUS_VARIANT[status]} className={className}>
      {EMPLOYMENT_STATUS_LABELS[status]}
    </Badge>
  );
}

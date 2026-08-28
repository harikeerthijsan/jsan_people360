import Link from 'next/link';
import * as React from 'react';

import { EmploymentStatusBadge } from '@/components/common/employment-status-badge';
import { UserAvatar } from '@/components/common/user-avatar';
import { Card, CardContent } from '@/components/ui/card';
import type { EmployeeRecord, EmployeeSummary } from '@/features/employees/types/employee.types';
import { cn } from '@/lib/utils';

/**
 * A person as a compact card: photo, name, staff code, placement, status.
 *
 * Used where a table row would be too dense to scan -- the dashboard's recent
 * joiners, a manager's direct reports, a picker's results.
 */

interface EmployeeCardProps {
  /** Accepts a full record or a summary, since most callers only have one. */
  employee: Pick<EmployeeRecord, 'id' | 'employee_code' | 'full_name' | 'employment_status'> & {
    photo_url?: string | null;
    official_email?: string;
    organization?: EmployeeRecord['organization'];
    deleted_at?: string | null;
  };
  /** Wraps the card in a link to the profile when set. */
  href?: string;
  /** Rendered at the end of the card -- an action menu, a remove button. */
  actions?: React.ReactNode;
  className?: string;
}

export function EmployeeCard({ employee, href, actions, className }: EmployeeCardProps): React.JSX.Element {
  const designation = employee.organization?.designation?.name;
  const team = employee.organization?.team?.name;
  const subtitle = [designation, team].filter(Boolean).join(' · ');

  const body = (
    <CardContent className="flex items-center gap-3 p-4">
      <UserAvatar name={employee.full_name} photoUrl={employee.photo_url} size="lg" />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-medium">{employee.full_name}</p>
          <EmploymentStatusBadge status={employee.employment_status} archived={employee.deleted_at != null} />
        </div>

        <p className="text-muted-foreground truncate font-mono text-xs">{employee.employee_code}</p>

        {subtitle ? <p className="text-muted-foreground mt-1 truncate text-sm">{subtitle}</p> : null}
      </div>

      {actions !== undefined ? <div className="shrink-0">{actions}</div> : null}
    </CardContent>
  );

  if (href === undefined) {
    return <Card className={className}>{body}</Card>;
  }

  return (
    <Card className={cn('hover:border-primary/50 focus-within:border-primary transition-colors', className)}>
      {/* The link wraps the content rather than the Card, so the focus ring
          follows the card's own border radius. */}
      <Link href={href} className="block rounded-[inherit] outline-none">
        {body}
      </Link>
    </Card>
  );
}

interface EmployeeSummaryCardProps {
  employee: EmployeeSummary;
  href?: string;
  className?: string;
}

/** The same card from an embedded `EmployeeSummary`, which carries less. */
export function EmployeeSummaryCard({
  employee,
  href,
  className,
}: EmployeeSummaryCardProps): React.JSX.Element {
  return <EmployeeCard employee={employee} href={href} className={className} />;
}

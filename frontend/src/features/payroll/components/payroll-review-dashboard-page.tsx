'use client';

import Link from 'next/link';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { usePayrollRuns } from '@/features/payroll/hooks';
import {
  RUN_STATUS_LABELS,
  formatMoney,
  type PayrollRun,
  type PayrollRunStatus,
} from '@/features/payroll/types';

/**
 * The review dashboard: every run that has numbers to look at, with its
 * exception load front and centre. The dashboard highlights; it decides
 * nothing — resolving, adjusting and signing off live on the run's review
 * page, each behind its own permission.
 */

const REVIEWABLE: readonly PayrollRunStatus[] = [
  'requires_review',
  'calculated',
  'in_review',
  'review_complete',
  'returned',
];

const STATUS_VARIANT: Record<PayrollRunStatus, 'secondary' | 'outline' | 'destructive'> = {
  draft: 'outline',
  calculating: 'outline',
  requires_review: 'destructive',
  calculated: 'secondary',
  in_review: 'secondary',
  review_complete: 'secondary',
  pending_approval: 'secondary',
  returned: 'destructive',
  approved: 'secondary',
  finalized: 'secondary',
};

export function PayrollReviewDashboardPage(): React.JSX.Element {
  const runs = usePayrollRuns({ page_size: 100 });
  const reviewable = (runs.data?.items ?? []).filter((run) => REVIEWABLE.includes(run.status));

  const columns: DataTableColumn<PayrollRun>[] = [
    {
      id: 'run',
      header: 'Run',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.period.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.run_code}</div>
        </div>
      ),
    },
    { id: 'employees', header: 'Employees', cell: (row) => row.employee_count },
    { id: 'net', header: 'Net payroll', cell: (row) => formatMoney(row.total_net, row.currency) },
    {
      id: 'flags',
      header: 'Needs attention',
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.open_critical_count > 0 ? (
            <Badge variant="destructive">{row.open_critical_count} critical</Badge>
          ) : null}
          {row.open_exception_count > row.open_critical_count ? (
            <Badge variant="outline">
              {row.open_exception_count - row.open_critical_count} other exceptions
            </Badge>
          ) : null}
          {row.review_count > 0 ? (
            <Badge variant="destructive">{row.review_count} records to review</Badge>
          ) : null}
          {row.open_exception_count === 0 && row.review_count === 0 ? (
            <span className="text-muted-foreground text-sm">Clear</span>
          ) : null}
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={STATUS_VARIANT[row.status]}>{RUN_STATUS_LABELS[row.status]}</Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollRunReview(row.id)}>Review</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollRunReconciliation(row.id)}>Reconciliation</Link>
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Review"
        description="Calculated runs awaiting review. Critical exceptions block completion; everything else informs the reviewer without deciding for them."
      />
      <DataTable
        rows={reviewable}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={runs.isLoading}
        error={runs.error}
        emptyTitle="Nothing to review"
        emptyDescription="A run appears here once it has been calculated."
      />
    </div>
  );
}

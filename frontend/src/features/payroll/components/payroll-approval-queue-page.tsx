'use client';

import Link from 'next/link';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { useApprovalQueue } from '@/features/payroll/hooks';
import { formatMoney, type PayrollRun } from '@/features/payroll/types';

/**
 * The approval queue: runs submitted and waiting for a decision. Everything
 * an approver weighs is on the row — totals, adjustments, exceptions, who
 * reviewed and who submitted — and the decision itself lives on the run's
 * approval page, behind its own permission.
 */

export function PayrollApprovalQueuePage(): React.JSX.Element {
  const queue = useApprovalQueue();

  const columns: DataTableColumn<PayrollRun>[] = [
    {
      id: 'run',
      header: 'Payroll period',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.period.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.run_code}</div>
        </div>
      ),
    },
    { id: 'employees', header: 'Employees', cell: (row) => row.employee_count },
    { id: 'gross', header: 'Gross', cell: (row) => formatMoney(row.total_gross, row.currency) },
    {
      id: 'deductions',
      header: 'Deductions',
      cell: (row) => formatMoney(row.total_deductions, row.currency),
    },
    { id: 'net', header: 'Net payroll', cell: (row) => formatMoney(row.total_net, row.currency) },
    {
      id: 'signals',
      header: 'Adjustments · Exceptions',
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.adjustment_count > 0 ? (
            <Badge variant="outline">{row.adjustment_count} adjustments</Badge>
          ) : null}
          {row.open_critical_count > 0 ? (
            <Badge variant="destructive">{row.open_critical_count} critical</Badge>
          ) : row.open_exception_count > 0 ? (
            <Badge variant="outline">{row.open_exception_count} open exceptions</Badge>
          ) : null}
          {row.adjustment_count === 0 && row.open_exception_count === 0 ? (
            <span className="text-muted-foreground text-sm">Clean</span>
          ) : null}
        </div>
      ),
    },
    {
      id: 'people',
      header: 'Reviewed · Submitted',
      cell: (row) => (
        <div className="text-sm">
          <div>{row.review_completed_by_name ?? '—'}</div>
          <div className="text-muted-foreground text-xs">
            {row.submitted_by_name ?? '—'}
            {row.submitted_at ? ` · ${new Date(row.submitted_at).toLocaleDateString()}` : ''}
          </div>
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button asChild size="sm" variant="outline">
          <Link href={routes.payrollRunApproval(row.id)}>Open</Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Approval"
        description="Runs submitted for approval. Approving, returning and finalizing are separate permissions, and the gates are enforced by the server on every decision."
      />
      <DataTable
        rows={queue.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={queue.isLoading}
        error={queue.error}
        emptyTitle="Nothing waiting for approval"
        emptyDescription="A run appears here once its review is complete and it has been submitted."
      />
    </div>
  );
}

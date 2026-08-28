'use client';

import Link from 'next/link';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { usePayrollHistory } from '@/features/payroll/hooks';
import { RUN_STATUS_LABELS, formatMoney, type PayrollRun } from '@/features/payroll/types';

/**
 * Finalized payroll history: the read-only record of what was paid, run by
 * run. Opening a run shows the same run pages — every mutation on them is
 * refused by the server for a finalized run.
 */

export function PayrollHistoryPage(): React.JSX.Element {
  const history = usePayrollHistory();

  const columns: DataTableColumn<PayrollRun>[] = [
    {
      id: 'period',
      header: 'Period',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.period.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.run_code}</div>
        </div>
      ),
    },
    { id: 'pay-date', header: 'Pay date', cell: (row) => row.period.pay_date },
    { id: 'employees', header: 'Employees', cell: (row) => row.employee_count },
    { id: 'gross', header: 'Gross', cell: (row) => formatMoney(row.total_gross, row.currency) },
    {
      id: 'deductions',
      header: 'Deductions',
      cell: (row) => formatMoney(row.total_deductions, row.currency),
    },
    { id: 'net', header: 'Net', cell: (row) => formatMoney(row.total_net, row.currency) },
    {
      id: 'signoff',
      header: 'Approved · Finalized by',
      cell: (row) => (
        <div className="text-sm">
          <div>{row.approved_by_name ?? '—'}</div>
          <div className="text-muted-foreground text-xs">
            {row.finalized_by_name ?? '—'}
            {row.finalized_at ? ` · ${new Date(row.finalized_at).toLocaleDateString()}` : ''}
          </div>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="secondary">{RUN_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollRunApproval(row.id)}>Approval record</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollRunDetail(row.id)}>Open</Link>
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll History"
        description="Finalized payroll runs — read-only. Each carries its immutable per-employee snapshots, unaffected by anything that changed since."
      />
      <DataTable
        rows={history.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={history.isLoading}
        error={history.error}
        emptyTitle="No finalized payroll yet"
        emptyDescription="A run appears here once it has been approved and finalized."
      />
    </div>
  );
}

'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { useCreateSettlement, useExitingEmployees } from '@/features/payroll/hooks';
import { SETTLEMENT_STATUS_LABELS, type EligibleExitRow, type SettlementListStatus } from '@/features/payroll/types';

/**
 * Exiting employees — every non-cancelled offboarding case — with where
 * their full & final settlement has got to. Opening a settlement reads the
 * offboarding module; it never starts a resignation of its own.
 */

const STATUS_VARIANT: Record<SettlementListStatus, 'outline' | 'secondary' | 'destructive'> = {
  not_started: 'outline',
  draft: 'outline',
  under_review: 'secondary',
  approved: 'secondary',
  settled: 'secondary',
};

export function PayrollSettlementsPage(): React.JSX.Element {
  const exits = useExitingEmployees();
  const create = useCreateSettlement();

  const columns: DataTableColumn<EligibleExitRow>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.employee.full_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.employee.employee_code}</div>
        </div>
      ),
    },
    { id: 'department', header: 'Department', cell: (row) => row.department ?? '—' },
    { id: 'joined', header: 'Joining date', cell: (row) => row.joining_date ?? '—' },
    { id: 'lwd', header: 'Last working date', cell: (row) => row.last_working_date },
    {
      id: 'exit',
      header: 'Exit',
      cell: (row) => (
        <div>
          <div className="capitalize">{row.exit_type}</div>
          <div className="text-muted-foreground text-xs">{row.exit_reason ?? '—'}</div>
        </div>
      ),
    },
    { id: 'period', header: 'Final payroll period', cell: (row) => row.final_period_name ?? '—' },
    {
      id: 'status',
      header: 'Settlement',
      cell: (row) => (
        <div className="space-y-1">
          <Badge variant={STATUS_VARIANT[row.settlement_status]}>{SETTLEMENT_STATUS_LABELS[row.settlement_status]}</Badge>
          {!row.eligible && row.ineligibility_reason ? (
            <div className="text-muted-foreground max-w-xs text-xs">{row.ineligibility_reason}</div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) =>
        row.settlement_id ? (
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollSettlement(row.settlement_id)}>Open</Link>
          </Button>
        ) : (
          <Can permission="payroll:settlement_create">
            <Button
              size="sm"
              disabled={!row.eligible}
              isLoading={create.isPending}
              onClick={() => create.mutate(row.offboarding_case_id)}
            >
              Start settlement
            </Button>
          </Can>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Full & Final Settlement"
        description="Exiting employees from the offboarding module. A settlement is opened deliberately — never merely because someone resigned — and computed only from data the application already holds."
      />
      <DataTable
        rows={exits.data ?? []}
        columns={columns}
        getRowId={(row) => row.offboarding_case_id}
        isLoading={exits.isLoading}
        error={exits.error}
        emptyTitle="No exiting employees"
        emptyDescription="Employees appear here once an offboarding case exists for them."
      />
    </div>
  );
}

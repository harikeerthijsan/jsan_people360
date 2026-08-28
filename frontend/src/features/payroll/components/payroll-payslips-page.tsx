'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { routes } from '@/config/site';
import { usePayslip, usePayslips, useRegeneratePayslip } from '@/features/payroll/hooks';
import { PAYSLIP_STATUS_LABELS, formatMoney, type Payslip } from '@/features/payroll/types';

import { PayslipDocument, PayslipDownloadButton } from './payslip-document';

/**
 * The administrator's payslip register, filtered by employee, payroll
 * month, department or payslip number. Viewing, downloading, generating
 * and regenerating are each their own permission on the server; the
 * buttons here merely reflect them.
 */

const PAGE_SIZE = 20;

export function PayrollPayslipsPage(): React.JSX.Element {
  const [page, setPage] = React.useState(1);
  const [month, setMonth] = React.useState('');
  const [payslipNumber, setPayslipNumber] = React.useState('');
  const [employeeId, setEmployeeId] = React.useState('');
  const [teamId, setTeamId] = React.useState('');
  const query = usePayslips({
    page,
    page_size: PAGE_SIZE,
    month: month || undefined,
    payslip_number: payslipNumber || undefined,
    employee_id: employeeId || undefined,
    team_id: teamId || undefined,
  });
  const regenerate = useRegeneratePayslip();

  const columns: DataTableColumn<Payslip>[] = [
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
    {
      id: 'month',
      header: 'Payroll month',
      cell: (row) => (
        <div>
          <div>{row.payroll_month}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.payslip_number}</div>
        </div>
      ),
    },
    { id: 'pay-date', header: 'Pay date', cell: (row) => row.period.pay_date },
    { id: 'gross', header: 'Gross', cell: (row) => formatMoney(row.gross_earnings, row.currency) },
    {
      id: 'deductions',
      header: 'Deductions',
      cell: (row) => formatMoney(row.total_deductions, row.currency),
    },
    { id: 'net', header: 'Net pay', cell: (row) => formatMoney(row.net_pay, row.currency) },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div>
          <Badge variant="secondary">{PAYSLIP_STATUS_LABELS[row.status]}</Badge>
          {row.regenerated_at ? (
            <div className="text-muted-foreground text-xs">
              PDF regenerated {new Date(row.regenerated_at).toLocaleDateString()}
            </div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={routes.payrollEmployeePayslip(row.employee.id, row.id)}>View</Link>
          </Button>
          <Can permission="payroll:payslip_download">
            <PayslipDownloadButton payslipId={row.id} employeeId={row.employee.id} size="sm" />
          </Can>
          <Can permission="payroll:payslip_generate">
            <Button
              size="sm"
              variant="ghost"
              isLoading={regenerate.isPending}
              onClick={() => regenerate.mutate(row.id)}
            >
              Regenerate PDF
            </Button>
          </Can>
        </div>
      ),
    },
  ];

  const total = query.data?.meta.total_items ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const resetPage = (): void => setPage(1);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payslips"
        description="Official payslips rendered from finalized payroll. Regenerating rebuilds the PDF from the same snapshot — numbers and payslip numbers never change."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="filter-month">Payroll month</Label>
          <Input
            id="filter-month"
            type="month"
            value={month}
            onChange={(event) => {
              setMonth(event.target.value);
              resetPage();
            }}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="filter-number">Payslip number</Label>
          <Input
            id="filter-number"
            placeholder="PS-2026-08-…"
            value={payslipNumber}
            onChange={(event) => {
              setPayslipNumber(event.target.value);
              resetPage();
            }}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="filter-employee">Employee ID (UUID)</Label>
          <Input
            id="filter-employee"
            placeholder="Paste an employee id"
            value={employeeId}
            onChange={(event) => {
              setEmployeeId(event.target.value.trim());
              resetPage();
            }}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="filter-team">Department (team id)</Label>
          <Input
            id="filter-team"
            placeholder="Paste a team id"
            value={teamId}
            onChange={(event) => {
              setTeamId(event.target.value.trim());
              resetPage();
            }}
          />
        </div>
      </div>

      <DataTable
        rows={query.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No payslips"
        emptyDescription="Generate payslips from a finalized run on its approval page, or widen the filters."
      />
      {pages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {page} of {pages} · {total} payslips
          </span>
          <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function PayrollEmployeePayslipPage({
  employeeId,
  payslipId,
}: {
  employeeId: string;
  payslipId: string;
}): React.JSX.Element {
  const query = usePayslip(employeeId, payslipId);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  const payslip = query.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${payslip.employee.full_name} · ${payslip.payroll_month}`}
        description={payslip.payslip_number}
        actions={
          <Button asChild variant="outline">
            <Link href={routes.payrollPayslips}>All payslips</Link>
          </Button>
        }
      />
      <PayslipDocument payslip={payslip} employeeId={employeeId} />
    </div>
  );
}

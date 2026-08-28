'use client';

import { FileText } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { useMyPayslip, useMyPayslips } from '@/features/payroll/hooks';
import { PAYSLIP_STATUS_LABELS, formatMoney, type Payslip } from '@/features/payroll/types';

import { PayslipDocument, PayslipDownloadButton } from './payslip-document';

/**
 * The employee's own payslips. Every call here goes through /me — there is
 * no employee id anywhere in this screen to get wrong — and only finalized
 * payroll ever produces a row.
 */

const PAGE_SIZE = 12;

export function MyPayslipsPage(): React.JSX.Element {
  const [page, setPage] = React.useState(1);
  const query = useMyPayslips({ page, page_size: PAGE_SIZE });

  const columns: DataTableColumn<Payslip>[] = [
    {
      id: 'month',
      header: 'Payroll month',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.payroll_month}</div>
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
    {
      id: 'net',
      header: 'Net pay',
      cell: (row) => <span className="font-medium">{formatMoney(row.net_pay, row.currency)}</span>,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="secondary">{PAYSLIP_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={routes.myPayslip(row.id)}>View</Link>
          </Button>
          <PayslipDownloadButton payslipId={row.id} size="sm" />
        </div>
      ),
    },
  ];

  const total = query.data?.meta.total_items ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Payslips"
        description="Official payslips from finalized payroll, newest first."
        actions={
          <Button asChild variant="outline">
            <Link href={routes.myPayroll}>My payroll</Link>
          </Button>
        }
      />
      {query.data && total === 0 ? (
        <EmptyState
          icon={FileText}
          title="No payslips yet"
          description="A payslip appears here once a payroll period has been finalized and published."
        />
      ) : (
        <>
          <DataTable
            rows={query.data?.items ?? []}
            columns={columns}
            getRowId={(row) => row.id}
            isLoading={query.isLoading}
            error={query.error}
            emptyTitle="No payslips yet"
            emptyDescription="A payslip appears here once a payroll period has been finalized."
          />
          {pages > 1 ? (
            <div className="flex items-center justify-end gap-2 text-sm">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="text-muted-foreground">
                Page {page} of {pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export function MyPayslipPage({ payslipId }: { payslipId: string }): React.JSX.Element {
  const query = useMyPayslip(payslipId);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  const payslip = query.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`Payslip · ${payslip.payroll_month}`}
        description={payslip.payslip_number}
        actions={
          <Button asChild variant="outline">
            <Link href={routes.myPayslips}>All payslips</Link>
          </Button>
        }
      />
      <PayslipDocument payslip={payslip} />
    </div>
  );
}

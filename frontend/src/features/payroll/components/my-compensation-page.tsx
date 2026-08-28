'use client';

import { FileText, Wallet } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { useMyCompensation, useMyPayslips, useMySalaryHistory } from '@/features/payroll/hooks';
import { formatMoney } from '@/features/payroll/types';

import {
  ComponentBreakdown,
  CompensationRecordsTable,
  CompensationSummary,
  SalaryHistoryTable,
} from './compensation-view';
import { PayslipDownloadButton } from './payslip-document';

/**
 * The employee's own payroll home.
 *
 * Read-only by construction: the backing endpoints live under /me, take no
 * employee id, and payroll has no self-service write anywhere. The latest
 * official payslip leads; what follows is the current compensation and its
 * history — exactly what an administrator sees on the salary page, because
 * it is the caller's own pay.
 */

export function MyCompensationPage(): React.JSX.Element {
  const query = useMyCompensation();
  const history = useMySalaryHistory();
  const payslips = useMyPayslips({ page: 1, page_size: 4 });

  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;

  const data = query.data;
  const latest = payslips.data?.items[0];
  const previous = payslips.data?.items.slice(1) ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Payroll"
        description="Your latest payslip, your salary structure, and every change ever made to your pay."
        actions={
          <Button asChild variant="outline">
            <Link href={routes.myPayslips}>
              <FileText className="mr-1 size-4" /> All payslips
            </Link>
          </Button>
        }
      />

      {payslips.isPending ? (
        <LoadingState />
      ) : latest ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center justify-between gap-2">
              <span>Latest payslip · {latest.payroll_month}</span>
              <span className="text-muted-foreground font-mono text-xs font-normal">
                {latest.payslip_number}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard label="Gross pay" value={formatMoney(latest.gross_earnings, latest.currency)} />
              <StatCard
                label="Total deductions"
                value={formatMoney(latest.total_deductions, latest.currency)}
              />
              <StatCard label="Net pay" value={formatMoney(latest.net_pay, latest.currency)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link href={routes.myPayslip(latest.id)}>View payslip</Link>
              </Button>
              <PayslipDownloadButton payslipId={latest.id} />
            </div>
            {previous.length > 0 ? (
              <div className="text-sm">
                <div className="text-muted-foreground mb-1 text-xs uppercase tracking-wide">
                  Previous payslips
                </div>
                {previous.map((row) => (
                  <div key={row.id} className="flex items-center justify-between border-b py-2">
                    <Link href={routes.myPayslip(row.id)} className="hover:underline">
                      {row.payroll_month}
                    </Link>
                    <span>{formatMoney(row.net_pay, row.currency)}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={FileText}
          title="No payslips yet"
          description="A payslip appears here once a payroll period has been finalized and published."
        />
      )}

      {data.current === null ? (
        <EmptyState
          icon={Wallet}
          title="No compensation on record"
          description="Nothing has been assigned yet. Once HR sets up your salary it will appear here."
        />
      ) : (
        <>
          <CompensationSummary record={data.current} />
          <ComponentBreakdown record={data.current} />
        </>
      )}

      {data.records.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Salary history</CardTitle>
          </CardHeader>
          <CardContent>
            <CompensationRecordsTable records={data.records} isLoading={false} error={null} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Salary revisions</CardTitle>
        </CardHeader>
        <CardContent>
          <SalaryHistoryTable
            entries={history.data ?? []}
            isLoading={history.isLoading}
            error={history.error}
          />
        </CardContent>
      </Card>
    </div>
  );
}

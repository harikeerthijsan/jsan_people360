'use client';

import { CalendarClock, ClipboardCheck, UserRoundPlus, Users } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { usePermitted } from '@/components/common/can';
import { BarChart, DonutChart, LineChart } from '@/components/common/charts';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { useAuth } from '@/components/providers/auth-provider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { GrowthGlance } from '@/features/dashboard/components/growth-glance';
import { useHrAnalytics, useHrDashboard } from '@/features/hr/hooks';
import type { Trend } from '@/features/hr/types';
import { formatDateTime } from '@/lib/utils';

/**
 * The landing screen, kept sparse on purpose: four figures, four graphs, one
 * table, one list of things waiting on somebody. Everything else lives on
 * its own module page. Org-wide figures are fetched only when the caller may
 * see them (the same guards the endpoints apply).
 */

interface MonthRow {
  period: string;
  label: string;
  headcount: number | null;
  hires: number | null;
  leave: number | null;
  attendance: number | null;
}

const monthColumns: DataTableColumn<MonthRow>[] = [
  { id: 'month', header: 'Month', cell: (row) => row.label },
  { id: 'headcount', header: 'Headcount', align: 'right', cell: (row) => row.headcount ?? '—' },
  { id: 'hires', header: 'Hires', align: 'right', cell: (row) => row.hires ?? '—' },
  { id: 'leave', header: 'Leave requests', align: 'right', cell: (row) => row.leave ?? '—' },
  { id: 'attendance', header: 'Attendance', align: 'right', cell: (row) => row.attendance ?? '—' },
];

function mergeTrends(
  headcount: Trend[] = [],
  hires: Trend[] = [],
  leave: Trend[] = [],
  attendance: Trend[] = [],
): MonthRow[] {
  const rows = new Map<string, MonthRow>();
  const add = (series: Trend[], key: keyof Omit<MonthRow, 'period' | 'label'>): void => {
    for (const point of series) {
      const row = rows.get(point.period) ?? {
        period: point.period,
        label: point.label,
        headcount: null,
        hires: null,
        leave: null,
        attendance: null,
      };
      row[key] = point.count;
      rows.set(point.period, row);
    }
  };
  add(headcount, 'headcount');
  add(hires, 'hires');
  add(leave, 'leave');
  add(attendance, 'attendance');
  return [...rows.values()].sort((a, b) => b.period.localeCompare(a.period));
}

const points = (trend: Trend[] | undefined): { label: string; value: number }[] =>
  (trend ?? []).map((t) => ({ label: t.label, value: t.count }));

function Panel({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

const Empty = ({ text }: { text: string }): React.JSX.Element => (
  <p className="text-muted-foreground py-8 text-center text-sm">{text}</p>
);

export function HomeDashboard(): React.JSX.Element {
  const { user } = useAuth();
  const canSeeOrgFigures = usePermitted({ allOf: ['employees:view', 'employees:view_all'] });
  const canSeeTrends = usePermitted({ allOf: ['reports:view', 'employees:view_all'] });
  const dashboard = useHrDashboard(canSeeOrgFigures);
  const analytics = useHrAnalytics(canSeeTrends);
  const data = canSeeOrgFigures ? dashboard.data : undefined;
  const trends = canSeeTrends ? analytics.data : undefined;

  const attendanceMix = data?.attendance
    ? [
        { label: 'Present', value: data.attendance.present, color: 'var(--success)' },
        { label: 'Absent', value: data.attendance.absent, color: 'var(--destructive)' },
        { label: 'On leave', value: data.attendance.on_leave, color: 'var(--warning)' },
        { label: 'Late', value: data.attendance.late_arrivals, color: 'var(--chart-5)' },
      ].filter((slice) => slice.value > 0)
    : [];
  const waiting = data?.requests
    ? data.requests.documents_awaiting_review +
      data.requests.leave_without_a_manager +
      data.requests.regularizations_without_a_manager
    : undefined;
  const months = mergeTrends(
    trends?.headcount_trend,
    trends?.hiring_trend,
    trends?.leave_trend,
    trends?.attendance_trend,
  );

  return (
    <div className="space-y-8">
      <PageHeader
        title={`Welcome back, ${user?.full_name.split(' ')[0] ?? 'there'}`}
        description={
          user?.last_login_at
            ? `Last signed in on ${formatDateTime(user.last_login_at)}`
            : 'This is your first sign-in.'
        }
        actions={
          <Button asChild size="sm" variant="outline">
            <Link href={routes.myDashboard}>My workspace</Link>
          </Button>
        }
      />

      <GrowthGlance />

      {!canSeeOrgFigures ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-6">
            <p className="text-muted-foreground text-sm">
              Your attendance, leave, timesheets, payslips, requests and notices are in My Workspace.
            </p>
            <Button asChild size="sm">
              <Link href={routes.myDashboard}>Open My Dashboard</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Active employees"
              value={data?.employees?.total_active ?? '—'}
              hint={
                data?.employees
                  ? `${String(data.employees.new_joiners_this_month)} joined this month`
                  : undefined
              }
              icon={Users}
              tone="blue"
            />
            <StatCard
              label="Present today"
              value={data?.attendance?.present ?? '—'}
              hint={
                data?.attendance
                  ? `${String(data.attendance.monthly_attendance_percentage)}% attendance this month`
                  : undefined
              }
              icon={CalendarClock}
              tone="green"
            />
            <StatCard
              label="Open requisitions"
              value={data?.recruitment?.open_requisitions ?? '—'}
              hint={
                data?.recruitment ? `${String(data.recruitment.offers_pending)} offers pending` : undefined
              }
              icon={UserRoundPlus}
              tone="orange"
            />
            <StatCard
              label="Waiting on somebody"
              value={waiting ?? '—'}
              hint={data?.requests ? `oldest ${String(data.requests.oldest_waiting_days)} day(s)` : undefined}
              icon={ClipboardCheck}
              tone="red"
            />
          </div>

          <div className="stagger grid gap-6 lg:grid-cols-3">
            <Panel title="Headcount" className="lg:col-span-2">
              {points(trends?.headcount_trend).length ? (
                <LineChart
                  data={points(trends?.headcount_trend)}
                  ariaLabel="Headcount by month"
                  area
                  height={220}
                />
              ) : (
                <Empty text="Headcount history appears once employees exist." />
              )}
            </Panel>
            <Panel title="Attendance today">
              {attendanceMix.length ? (
                <DonutChart
                  data={attendanceMix}
                  ariaLabel="Attendance today"
                  centerValue={data?.attendance?.present ?? 0}
                  centerLabel="present"
                  className="justify-center"
                />
              ) : (
                <Empty text="No attendance recorded today." />
              )}
            </Panel>
          </div>

          <div className="stagger grid gap-6 lg:grid-cols-2">
            <Panel title="Hires by month">
              {points(trends?.hiring_trend).length ? (
                <BarChart
                  data={points(trends?.hiring_trend)}
                  ariaLabel="Hires by month"
                  color="var(--chart-2)"
                />
              ) : (
                <Empty text="Joiners appear here month by month." />
              )}
            </Panel>
            <Panel title="Leave requests by month">
              {points(trends?.leave_trend).length ? (
                <BarChart
                  data={points(trends?.leave_trend)}
                  ariaLabel="Leave requests by month"
                  color="var(--chart-3)"
                />
              ) : (
                <Empty text="Leave requests appear here once they are filed." />
              )}
            </Panel>
          </div>

          <div className="stagger grid gap-6 lg:grid-cols-3">
            <Panel title="Month by month" className="lg:col-span-2">
              <DataTable
                flush
                rows={months}
                columns={monthColumns}
                getRowId={(row) => row.period}
                isLoading={analytics.isLoading}
                error={analytics.error}
                emptyTitle="No history yet"
                emptyDescription="Monthly figures appear once there is activity to count."
              />
            </Panel>
            <Panel title="Waiting on somebody">
              {data?.leave && data.requests ? (
                <ul className="divide-y text-sm">
                  {(
                    [
                      ['Pending leave requests', data.leave.pending_requests],
                      ['Leave without a manager', data.requests.leave_without_a_manager],
                      ['Regularizations without a manager', data.requests.regularizations_without_a_manager],
                      ['Documents awaiting review', data.requests.documents_awaiting_review],
                      ['Offers pending', data.recruitment?.offers_pending ?? 0],
                    ] as const
                  ).map(([label, value]) => (
                    <li key={label} className="flex items-center justify-between py-2.5">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-medium tabular-nums">{value}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty text="Nothing is waiting." />
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

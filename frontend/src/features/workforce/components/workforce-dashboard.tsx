'use client';

import { CalendarClock, CalendarOff, Clock, FileClock, Users, Wifi } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useWorkforceDashboard } from '@/features/workforce/hooks';
import type { CountByLabel } from '@/features/workforce/types';

/** A labelled count list, used for both breakdowns on this screen. */
function Breakdown({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: CountByLabel[];
}): React.JSX.Element {
  const total = rows.reduce((sum, row) => sum + row.count, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing recorded yet today.</p>
        ) : (
          rows.map((row) => (
            <div className="space-y-1" key={row.label}>
              <div className="flex justify-between text-sm">
                <span className="capitalize">{row.label.replaceAll('_', ' ')}</span>
                <b className="tabular-nums">{row.count}</b>
              </div>
              <div className="bg-muted h-1.5 rounded-full">
                <div
                  className="bg-primary h-full rounded-full"
                  style={{ width: `${String(total > 0 ? (row.count / total) * 100 : 0)}%` }}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

/** The day at a glance: who is in, who is out, and what is waiting on someone. */
export function WorkforceDashboard(): React.JSX.Element {
  const query = useWorkforceDashboard();

  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;

  const data = query.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workforce"
        description={`Attendance, leave and timesheets for ${data.on_date}.`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href="/attendance/calendar">Calendar</Link>
            </Button>
            <Button asChild>
              <Link href="/attendance/register">Attendance register</Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="Present" value={data.present} hint={`of ${String(data.headcount)}`} />
        <StatCard icon={CalendarOff} label="Absent" value={data.absent} />
        <StatCard icon={CalendarClock} label="On leave" value={data.on_leave} />
        <StatCard icon={Wifi} label="Working remotely" value={data.remote} />
        <StatCard icon={Clock} label="Late arrivals" value={data.late_arrivals} />
        <StatCard
          icon={FileClock}
          label="Missing timesheets"
          value={data.missing_timesheets}
          hint="this week"
        />
        <StatCard
          label="Attendance this month"
          value={`${String(data.monthly_attendance_percentage)}%`}
          hint="working days credited"
        />
        <StatCard
          label="Awaiting a decision"
          value={data.leave_requests_pending + data.regularizations_pending}
          hint={`${String(data.leave_requests_pending)} leave · ${String(data.regularizations_pending)} corrections`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Breakdown
          description="Where today's attendance was marked from."
          rows={data.by_work_mode}
          title="By work mode"
        />
        <Breakdown
          description="How today's records are classified."
          rows={data.by_attendance_status}
          title="By attendance status"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Waiting on a manager</CardTitle>
          <CardDescription>
            Requests hold a leave balance until they are decided, so a queue left standing blocks days the
            employee could otherwise use.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/leave/approvals">Leave requests ({String(data.leave_requests_pending)})</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/attendance/regularizations">
              Attendance corrections ({String(data.regularizations_pending)})
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/timesheets/approvals">Timesheets</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

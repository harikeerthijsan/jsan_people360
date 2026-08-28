'use client';

import {
  AlertCircle,
  BriefcaseBusiness,
  CalendarDays,
  CalendarOff,
  ClipboardCheck,
  FileClock,
  TrendingUp,
  UserCheck,
  UserX,
  Users2,
} from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { QuickActions } from '@/features/manager/components/quick-actions';
import { TeamMemberCell, formatDay } from '@/features/manager/components/widgets';
import { useManagerDashboard } from '@/features/manager/hooks';

/**
 * The manager's home screen.
 *
 * Everything on it is about the people who report to the person looking at it.
 * There is deliberately no headcount, no company attendance percentage and no
 * organization-wide pending count: those belong to the workforce dashboard, and
 * mixing them in would make it impossible to tell at a glance whether a number
 * is about your team.
 *
 * One request builds the whole page, for the reason the employee dashboard
 * gives about its own: a query per widget makes the first screen after signing
 * in as slow as its slowest corner.
 */
export function ManagerDashboard(): React.JSX.Element {
  const dashboard = useManagerDashboard();

  if (dashboard.isPending) return <LoadingState message="Loading your team…" />;
  if (dashboard.error) {
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  }

  const data = dashboard.data;
  const waiting =
    data.pending_leave_approvals +
    data.pending_timesheet_approvals +
    data.pending_regularizations +
    data.pending_performance_reviews;

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Team"
        description={`${String(data.team_size)} direct report(s) · everything here is your reporting line only.`}
      />

      {waiting > 0 ? (
        <Card className="border-amber-300 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <AlertCircle className="size-4" aria-hidden="true" />
              Waiting on you
            </CardTitle>
            <CardDescription>
              Requests from your team. Your own requests are not here — they go to your manager.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {data.pending_leave_approvals > 0 ? (
              <Button asChild size="sm" variant="outline">
                <Link href={`${routes.managerLeave}?status=pending`}>
                  {data.pending_leave_approvals} leave request(s)
                </Link>
              </Button>
            ) : null}
            {data.pending_timesheet_approvals > 0 ? (
              <Button asChild size="sm" variant="outline">
                <Link href={`${routes.managerTimesheets}?status=submitted`}>
                  {data.pending_timesheet_approvals} timesheet(s)
                </Link>
              </Button>
            ) : null}
            {data.pending_regularizations > 0 ? (
              <Button asChild size="sm" variant="outline">
                <Link href={routes.managerRegularization}>{data.pending_regularizations} correction(s)</Link>
              </Button>
            ) : null}
            {data.pending_performance_reviews > 0 ? (
              <Button asChild size="sm" variant="outline">
                <Link href={routes.managerPerformance}>
                  {data.pending_performance_reviews} performance review(s)
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <QuickActions />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard hint="direct reports" icon={Users2} label="Team members" value={data.team_size} />
        <StatCard hint="today" icon={UserCheck} label="Present" value={data.present_today} />
        <StatCard hint="today" icon={UserX} label="Absent" value={data.absent_today} />
        <StatCard hint="today" icon={CalendarOff} label="On leave" value={data.on_leave_today} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          hint="awaiting your decision"
          icon={CalendarOff}
          label="Leave approvals"
          value={data.pending_leave_approvals}
        />
        <StatCard
          hint="awaiting your decision"
          icon={FileClock}
          label="Timesheet approvals"
          value={data.pending_timesheet_approvals}
        />
        <StatCard
          hint="awaiting your decision"
          icon={ClipboardCheck}
          label="Corrections"
          value={data.pending_regularizations}
        />
        <StatCard
          hint="self review in, yours not"
          icon={TrendingUp}
          label="Performance reviews"
          value={data.pending_performance_reviews}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <BriefcaseBusiness className="size-4" aria-hidden="true" />
              Allocation
            </CardTitle>
            <CardDescription>
              {data.active_projects} active project(s) across your team today.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Allocated</span>
              <span className="font-medium tabular-nums">{data.allocation.allocated_members}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">On the bench</span>
              <span className="font-medium tabular-nums">{data.allocation.unallocated_members}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Average allocation</span>
              <span className="font-medium tabular-nums">{data.allocation.average_allocation}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Billable</span>
              <span className="font-medium tabular-nums">{data.allocation.billable_members}</span>
            </div>
            <Button asChild className="mt-1" size="sm" variant="outline">
              <Link href={routes.managerProjects}>View projects</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <CalendarDays className="size-4" aria-hidden="true" />
              Upcoming team holidays
            </CardTitle>
            <CardDescription>For the locations your team works from.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.upcoming_holidays.length === 0 ? (
              <p className="text-muted-foreground text-sm">No holidays are scheduled.</p>
            ) : (
              <ul className="space-y-2">
                {data.upcoming_holidays.map((holiday) => (
                  <li className="flex items-center justify-between gap-3" key={holiday.id}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{holiday.name}</p>
                      <p className="text-muted-foreground truncate text-xs">{holiday.calendar_name}</p>
                    </div>
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {formatDay(holiday.holiday_date)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Leave awaiting a decision</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.leave_awaiting_decision.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing waiting.</p>
            ) : (
              <ul className="space-y-3">
                {data.leave_awaiting_decision.map((row) => (
                  <li key={row.request.id}>
                    <TeamMemberCell
                      detail={`${row.request.days} day(s) · ${formatDay(row.request.from_date)}`}
                      employee={row.employee}
                    />
                  </li>
                ))}
              </ul>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={`${routes.managerLeave}?status=pending`}>Open leave</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Timesheets awaiting a decision</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.timesheets_awaiting_decision.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing waiting.</p>
            ) : (
              <ul className="space-y-3">
                {data.timesheets_awaiting_decision.map((row) => (
                  <li key={row.timesheet.id}>
                    <TeamMemberCell
                      detail={`${row.timesheet.total_hours}h · week of ${formatDay(row.timesheet.week_start_date)}`}
                      employee={row.employee}
                    />
                  </li>
                ))}
              </ul>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={`${routes.managerTimesheets}?status=submitted`}>Open timesheets</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Corrections awaiting a decision</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.regularizations_awaiting_decision.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing waiting.</p>
            ) : (
              <ul className="space-y-3">
                {data.regularizations_awaiting_decision.map((row) => (
                  <li key={row.request.id}>
                    <TeamMemberCell detail={formatDay(row.request.attendance_date)} employee={row.employee} />
                  </li>
                ))}
              </ul>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={routes.managerRegularization}>Open corrections</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      {data.not_recorded_today > 0 ? (
        <p className="text-muted-foreground text-sm">
          <Badge className="mr-2" variant="outline">
            {data.not_recorded_today}
          </Badge>
          team member(s) have no attendance recorded for today and are not on leave.
        </p>
      ) : null}
    </div>
  );
}

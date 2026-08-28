'use client';

import {
  AlertCircle,
  BriefcaseBusiness,
  CalendarDays,
  CalendarOff,
  Clock,
  FileClock,
  FileText,
  Megaphone,
} from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import {
  ApprovalStatusBadge,
  TimesheetStatusBadge,
  formatMinutes,
} from '@/components/common/workforce-widgets';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { AttendanceCard } from '@/features/self-service/components/attendance-card';
import { LeaveBalanceGrid } from '@/features/self-service/components/leave-balance-grid';
import { QuickActions } from '@/features/self-service/components/quick-actions';
import { useMyDashboard } from '@/features/self-service/hooks';

/**
 * The employee's home screen.
 *
 * Everything on it is about the person looking at it. There is deliberately no
 * headcount, no team figure and no company attendance percentage: those belong
 * to the HR dashboard, and mixing them in would make it impossible to tell at a
 * glance whether a number is about you.
 *
 * One request builds the whole page. The alternative -- a query per widget --
 * makes the first screen after signing in as slow as its slowest corner.
 */

function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

export function EmployeeDashboard(): React.JSX.Element {
  const dashboard = useMyDashboard();

  if (dashboard.isPending) return <LoadingState message="Loading your workspace…" />;
  if (dashboard.error) {
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  }

  const data = dashboard.data;
  const timesheet = data.current_timesheet;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Hello, ${data.employee.full_name.split(' ')[0] ?? ''}`}
        description={`${data.employee.employee_code} · everything here is yours alone.`}
      />

      {data.pending_actions.length > 0 ? (
        <Card className="border-amber-300 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <AlertCircle className="size-4" aria-hidden="true" />
              Waiting on you
            </CardTitle>
            <CardDescription>
              Only things you can act on. A request sitting with your manager is not listed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {data.pending_actions.map((action) => (
                <li className="flex flex-wrap items-center justify-between gap-2" key={action.code}>
                  <div>
                    <p className="text-sm font-medium">{action.label}</p>
                    {action.detail ? <p className="text-muted-foreground text-sm">{action.detail}</p> : null}
                  </div>
                  <Button asChild size="sm" variant="outline">
                    <Link href={action.link}>Open</Link>
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <QuickActions />

      <div className="grid gap-4 lg:grid-cols-3">
        <AttendanceCard className="lg:col-span-1" />

        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <StatCard
            hint="this month"
            icon={CalendarDays}
            label="Days present"
            value={data.month_summary.present_days}
          />
          <StatCard
            hint="this month"
            icon={Clock}
            label="Hours worked"
            value={formatMinutes(data.month_summary.worked_minutes)}
          />
          <StatCard
            hint="awaiting a decision"
            icon={CalendarOff}
            label="Leave requests"
            value={data.pending_leave.length}
          />
          <StatCard
            hint={`${String(data.documents.pending_review)} awaiting review`}
            icon={FileText}
            label="My documents"
            value={data.documents.total}
          />
        </div>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Leave balance</h2>
          <Button asChild size="sm" variant="ghost">
            <Link href={routes.myLeave}>View leave</Link>
          </Button>
        </div>
        <LeaveBalanceGrid balances={data.leave_balances} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <FileClock className="size-4" aria-hidden="true" />
              This week&apos;s timesheet
            </CardTitle>
            <CardDescription>Week beginning {dayLabel(data.current_week_start)}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {timesheet ? (
              <>
                <div className="flex items-center justify-between">
                  <p className="text-2xl font-semibold tabular-nums">
                    {timesheet.total_hours}
                    <span className="text-muted-foreground ml-1 text-sm font-normal">hours booked</span>
                  </p>
                  <TimesheetStatusBadge status={timesheet.status} />
                </div>
                <p className="text-muted-foreground text-sm">
                  {timesheet.billable_hours} billable · {timesheet.entries.length} entries
                </p>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Nothing booked for this week yet.</p>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={routes.myTimesheets}>Open timesheet</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <BriefcaseBusiness className="size-4" aria-hidden="true" />
              My projects
            </CardTitle>
            <CardDescription>Where your time is allocated today.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.projects.length === 0 ? (
              <p className="text-muted-foreground text-sm">You are not allocated to a project.</p>
            ) : (
              <ul className="space-y-2">
                {data.projects.slice(0, 4).map((project) => (
                  <li className="flex items-center justify-between gap-3" key={project.allocation_id}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{project.project_name}</p>
                      <p className="text-muted-foreground truncate text-xs">
                        {project.client_name ?? '—'}
                        {project.role ? ` · ${project.role}` : ''}
                      </p>
                    </div>
                    <Badge variant="outline">{project.allocation_percentage}%</Badge>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={routes.myProjects}>View all</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <CalendarOff className="size-4" aria-hidden="true" />
              Pending leave
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.pending_leave.length === 0 ? (
              <p className="text-muted-foreground text-sm">No requests are awaiting a decision.</p>
            ) : (
              <ul className="space-y-2">
                {data.pending_leave.map((request) => (
                  <li className="flex items-center justify-between gap-3" key={request.id}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{request.leave_type?.name ?? 'Leave'}</p>
                      <p className="text-muted-foreground text-xs tabular-nums">
                        {dayLabel(request.from_date)}
                        {request.from_date === request.to_date
                          ? ''
                          : ` → ${dayLabel(request.to_date)}`} · {request.days} day(s)
                      </p>
                    </div>
                    <ApprovalStatusBadge status={request.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <CalendarDays className="size-4" aria-hidden="true" />
              Upcoming holidays
            </CardTitle>
            <CardDescription>For your work location.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.upcoming_holidays.length === 0 ? (
              <p className="text-muted-foreground text-sm">No holidays are scheduled.</p>
            ) : (
              <ul className="space-y-2">
                {data.upcoming_holidays.map((holiday) => (
                  <li className="flex items-center justify-between gap-3" key={holiday.id}>
                    <p className="truncate text-sm font-medium">{holiday.name}</p>
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {dayLabel(holiday.holiday_date)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <FileText className="size-4" aria-hidden="true" />
              Recent documents
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.recent_documents.length === 0 ? (
              <EmptyState
                description="Anything you upload, and anything HR issues to you, appears here."
                title="Nothing filed yet"
              />
            ) : (
              <ul className="space-y-2">
                {data.recent_documents.map((document) => (
                  <li className="flex items-center justify-between gap-3" key={document.id}>
                    <p className="truncate text-sm font-medium">{document.name}</p>
                    <Badge variant={document.status === 'rejected' ? 'destructive' : 'outline'}>
                      {document.status.replace('_', ' ')}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href={routes.myDocuments}>Open my documents</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Megaphone className="size-4" aria-hidden="true" />
              Recent announcements
            </CardTitle>
            <CardDescription>Company notices addressed to you.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.recent_announcements.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing new.</p>
            ) : (
              <ul className="space-y-3">
                {data.recent_announcements.map((item) => (
                  <li key={item.id}>
                    <p className="text-sm font-medium">{item.title}</p>
                    <p className="text-muted-foreground text-sm">{item.summary ?? item.body}</p>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild variant="outline" size="sm">
              <Link href={routes.myAnnouncements}>Open the notice board</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

'use client';

import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { UserAvatar } from '@/components/common/user-avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { TeamAttendanceBadge, formatDay, formatMinutes } from '@/features/manager/components/widgets';
import { useTeamMember } from '@/features/manager/hooks';
import { EMPLOYMENT_STATUS_LABELS } from '@/features/manager/types';

/**
 * One team member, as their manager sees them.
 *
 * Deliberately not the HR employee profile. There is no salary, no bank
 * detail, no statutory identifier and no home address on this screen, and not
 * because they are hidden: the endpoint behind it does not return them. A
 * manager who genuinely needs one reaches the employee module, which is guarded
 * separately and audits the access.
 *
 * A member of another manager's team answers 403 here, so this screen shows an
 * error rather than a profile if the id in the URL is edited.
 */
export function TeamMemberPage({ employeeId }: { employeeId: string }): React.JSX.Element {
  const profile = useTeamMember(employeeId);

  if (profile.isPending) return <LoadingState message="Loading this team member…" />;
  if (profile.error) {
    return (
      <div className="space-y-4">
        <Button asChild size="sm" variant="ghost">
          <Link href={routes.managerTeam}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to my team
          </Link>
        </Button>
        <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />
      </div>
    );
  }

  const data = profile.data;
  const member = data.member;

  return (
    <div className="space-y-6">
      <Button asChild size="sm" variant="ghost">
        <Link href={routes.managerTeam}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to my team
        </Link>
      </Button>

      <PageHeader
        title={member.full_name}
        description={`${member.employee_code} · ${member.designation?.name ?? 'No designation recorded'}`}
        actions={<TeamAttendanceBadge status={member.attendance_status} />}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Basic information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <UserAvatar name={member.full_name} photoUrl={member.photo_url} size="lg" />
              <div className="min-w-0">
                <p className="truncate font-medium">{member.full_name}</p>
                <p className="text-muted-foreground truncate text-sm">{member.official_email}</p>
              </div>
            </div>

            <dl className="space-y-2 text-sm">
              {[
                ['Designation', member.designation?.name],
                ['Business unit', member.business_unit?.name],
                ['Team', member.team?.name],
                ['Location', member.work_location?.name],
                ['Employment type', member.employment_type?.name],
                ['Work mode', data.work_mode],
                ['Joined', formatDay(data.joining_date)],
                ['Confirmed', data.confirmation_date ? formatDay(data.confirmation_date) : null],
                ['Reports to', data.reporting_manager?.full_name],
              ].map(([label, value]) => (
                <div className="flex items-start justify-between gap-3" key={label}>
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="text-right font-medium">{value ?? '—'}</dd>
                </div>
              ))}
              <div className="flex items-start justify-between gap-3">
                <dt className="text-muted-foreground">Status</dt>
                <dd>
                  <Badge variant="outline">{EMPLOYMENT_STATUS_LABELS[member.employment_status]}</Badge>
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard hint="this month" label="Present" value={data.attendance.present_days} />
            <StatCard hint="this month" label="Absent" value={data.attendance.absent_days} />
            <StatCard hint="this month" label="On leave" value={data.attendance.leave_days} />
            <StatCard
              hint="this month"
              label="Hours worked"
              value={formatMinutes(data.attendance.worked_minutes)}
            />
          </section>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Attendance summary</CardTitle>
              <CardDescription>
                {formatDay(data.attendance.from_date)} to {formatDay(data.attendance.to_date)}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              {[
                ['Half days', data.attendance.half_days],
                ['Late arrivals', data.attendance.late_arrivals],
                ['Early exits', data.attendance.early_exits],
                ['Overtime', formatMinutes(data.attendance.overtime_minutes)],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <p className="text-muted-foreground text-xs">{label}</p>
                  <p className="font-medium tabular-nums">{value}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Leave summary</CardTitle>
            </CardHeader>
            <CardContent>
              {data.leave.length === 0 ? (
                <p className="text-muted-foreground text-sm">No leave types are configured.</p>
              ) : (
                <ul className="space-y-2">
                  {data.leave.map((balance) => (
                    <li
                      className="flex items-center justify-between gap-3 text-sm"
                      key={balance.leave_type_id}
                    >
                      <span className="truncate">{balance.leave_type_name}</span>
                      <span className="text-muted-foreground tabular-nums">
                        {balance.available} available · {balance.used} taken
                        {Number(balance.pending) > 0 ? ` · ${balance.pending} awaiting you` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Timesheets</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {[
                  ['Draft', data.timesheets.draft],
                  ['Submitted', data.timesheets.submitted],
                  ['Approved', data.timesheets.approved],
                  ['Returned', data.timesheets.rejected],
                  ['Total hours', data.timesheets.total_hours],
                  ['Billable hours', data.timesheets.billable_hours],
                ].map(([label, value]) => (
                  <div className="flex items-center justify-between" key={String(label)}>
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-medium tabular-nums">{value}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Project allocation</CardTitle>
              </CardHeader>
              <CardContent>
                {member.allocations.length === 0 ? (
                  <p className="text-muted-foreground text-sm">On the bench today.</p>
                ) : (
                  <ul className="space-y-2">
                    {member.allocations.map((allocation) => (
                      <li className="flex items-center justify-between gap-3" key={allocation.project_id}>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{allocation.project_name}</p>
                          <p className="text-muted-foreground truncate text-xs">
                            {allocation.client_name ?? '—'}
                            {allocation.billable ? '' : ' · non-billable'}
                          </p>
                        </div>
                        <Badge variant="outline">{allocation.allocation_percentage}%</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Performance</CardTitle>
              <CardDescription>
                {data.performance?.cycle_name ?? 'No active performance cycle.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              {data.performance ? (
                <>
                  <div>
                    <p className="text-muted-foreground text-xs">Goals</p>
                    <p className="font-medium tabular-nums">
                      {data.performance.goals_completed}/{data.performance.goals}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Progress</p>
                    <p className="font-medium tabular-nums">{data.performance.goal_progress}%</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Review</p>
                    <p className="font-medium">{data.performance.manager_review_status ?? 'Not started'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Rating</p>
                    <p className="font-medium tabular-nums">{data.performance.current_rating ?? '—'}</p>
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground col-span-full text-sm">Nothing to show yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

'use client';

import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  APPROVAL_STATUS_LABELS,
  ATTENDANCE_STATUS_LABELS,
  SHIFT_TYPE_LABELS,
  TIMESHEET_STATUS_LABELS,
  WORK_MODE_LABELS,
  type ApprovalStatus,
  type AttendanceStatus,
  type CalendarDay,
  type LeaveBalance,
  type Shift,
  type TimesheetStatus,
  type WorkMode,
} from '@/features/workforce/types';

/**
 * The workforce module's shared pieces.
 *
 * Grouped in one file because they are small and always used together: an
 * attendance row carries a status badge and a worked-hours figure, a leave row
 * carries an approval badge, and the calendar reuses both. Splitting them
 * across seven files would mean seven imports on every screen and no clearer
 * boundary.
 */

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

const ATTENDANCE_VARIANT: Record<AttendanceStatus, BadgeVariant> = {
  present: 'success',
  absent: 'destructive',
  half_day: 'warning',
  on_leave: 'secondary',
  holiday: 'outline',
  weekly_off: 'outline',
};

const APPROVAL_VARIANT: Record<ApprovalStatus, BadgeVariant> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'destructive',
  cancelled: 'outline',
};

const TIMESHEET_VARIANT: Record<TimesheetStatus, BadgeVariant> = {
  draft: 'secondary',
  submitted: 'warning',
  approved: 'success',
  rejected: 'destructive',
};

export function AttendanceStatusBadge({ status }: { status: AttendanceStatus }): React.JSX.Element {
  return <Badge variant={ATTENDANCE_VARIANT[status]}>{ATTENDANCE_STATUS_LABELS[status]}</Badge>;
}

export function ApprovalStatusBadge({ status }: { status: ApprovalStatus }): React.JSX.Element {
  return <Badge variant={APPROVAL_VARIANT[status]}>{APPROVAL_STATUS_LABELS[status]}</Badge>;
}

export function TimesheetStatusBadge({ status }: { status: TimesheetStatus }): React.JSX.Element {
  return <Badge variant={TIMESHEET_VARIANT[status]}>{TIMESHEET_STATUS_LABELS[status]}</Badge>;
}

export function WorkModeBadge({ mode }: { mode: WorkMode }): React.JSX.Element {
  return <Badge variant="outline">{WORK_MODE_LABELS[mode]}</Badge>;
}

/**
 * Minutes rendered as people say them.
 *
 * "7h 45m", never "465 minutes" and never "7.75": a timesheet is discussed in
 * hours and minutes, and a decimal invites the reader to mistake 7.45 for
 * seven hours forty-five.
 */
export function formatMinutes(minutes: number): string {
  if (minutes <= 0) return '—';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${String(rest)}m`;
  if (rest === 0) return `${String(hours)}h`;
  return `${String(hours)}h ${String(rest)}m`;
}

/** A shift as one line: name, window and grace. */
export function ShiftSummary({ shift }: { shift: Shift }): React.JSX.Element {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="font-medium">{shift.name}</span>
        <Badge variant="outline">{SHIFT_TYPE_LABELS[shift.shift_type]}</Badge>
      </div>
      <p className="text-muted-foreground text-sm tabular-nums">
        {shift.start_time.slice(0, 5)} – {shift.end_time.slice(0, 5)}
        {shift.grace_minutes > 0 ? ` · ${String(shift.grace_minutes)} min grace` : ''}
      </p>
    </div>
  );
}

/**
 * One leave type's entitlement.
 *
 * Shows held days separately from spent ones. They behave differently -- held
 * days come back if the request is rejected -- and a single "used" figure that
 * silently includes both is the kind of number an employee will dispute.
 */
export function LeaveBalanceCard({ balance }: { balance: LeaveBalance }): React.JSX.Element {
  const allocated = Number(balance.allocated) + Number(balance.opening_balance);
  const remaining = Number(balance.remaining);
  const used = Number(balance.used);
  const pending = Number(balance.pending);
  const consumed = allocated > 0 ? Math.min(((used + pending) / allocated) * 100, 100) : 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          {balance.leave_type?.name ?? 'Leave'}
          {balance.leave_type && !balance.leave_type.is_paid ? (
            <Badge className="ml-2" variant="outline">
              Unpaid
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-2xl font-semibold tabular-nums">
          {balance.remaining}
          <span className="text-muted-foreground ml-1 text-sm font-normal">of {String(allocated)} left</span>
        </p>
        <div
          aria-label={`${balance.remaining} of ${String(allocated)} days remaining`}
          className="bg-muted h-2 rounded-full"
          role="img"
        >
          <div
            className={cn('h-full rounded-full', remaining <= 0 ? 'bg-destructive' : 'bg-primary')}
            style={{ width: `${String(consumed)}%` }}
          />
        </div>
        <p className="text-muted-foreground text-sm tabular-nums">
          {balance.used} taken
          {pending > 0 ? ` · ${balance.pending} awaiting a decision` : ''}
        </p>
      </CardContent>
    </Card>
  );
}

/** Colour for a calendar square, chosen so absence stands out and rest days recede. */
function dayTone(day: CalendarDay): string {
  if (day.holiday_name) return 'bg-primary-subtle border-primary/30';
  if (day.leave_type) return 'bg-amber-50 border-amber-200 dark:bg-amber-950/40 dark:border-amber-900';
  if (day.is_weekend) return 'bg-muted/60';
  if (day.attendance_status === 'absent') {
    return 'bg-destructive/10 border-destructive/30';
  }
  if (day.attendance_status === 'present' || day.attendance_status === 'half_day') {
    return 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-900';
  }
  return '';
}

const LEGEND: { tone: string; label: string }[] = [
  { tone: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/40', label: 'Worked' },
  { tone: 'bg-amber-50 border-amber-200 dark:bg-amber-950/40', label: 'Leave' },
  { tone: 'bg-primary-subtle border-primary/30', label: 'Holiday' },
  { tone: 'bg-destructive/10 border-destructive/30', label: 'Absent' },
  { tone: 'bg-muted/60', label: 'Weekly off' },
];

/**
 * A month of one employee's days.
 *
 * The grid is padded to start on the weekday the 1st actually falls on, so the
 * columns line up with a wall calendar. Without that padding every month reads
 * as if it began on a Monday.
 */
export function AttendanceCalendar({ days }: { days: CalendarDay[] }): React.JSX.Element {
  const leadingBlanks = React.useMemo(() => {
    const first = days[0];
    if (!first) return 0;
    // `getDay()` counts Sunday as 0; the grid starts on Monday.
    return (new Date(`${first.day}T00:00:00`).getDay() + 6) % 7;
  }, [days]);

  return (
    <div className="space-y-3">
      <div className="text-muted-foreground grid grid-cols-7 gap-1 text-center text-xs font-medium">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: leadingBlanks }, (_, index) => (
          <div aria-hidden="true" key={`blank-${String(index)}`} />
        ))}

        {days.map((day) => {
          const label = [
            day.day,
            day.holiday_name ?? '',
            day.leave_type ? `On ${day.leave_type}` : '',
            day.attendance_status ? ATTENDANCE_STATUS_LABELS[day.attendance_status] : '',
            day.worked_minutes > 0 ? formatMinutes(day.worked_minutes) : '',
          ]
            .filter(Boolean)
            .join(' · ');

          return (
            <div
              className={cn('min-h-16 rounded-md border p-1.5 text-xs', dayTone(day))}
              key={day.day}
              title={label}
            >
              <div className="font-medium tabular-nums">{Number(day.day.slice(8, 10))}</div>
              {day.holiday_name ? (
                <p className="text-primary line-clamp-2 leading-tight">{day.holiday_name}</p>
              ) : day.leave_type ? (
                <p className="line-clamp-2 leading-tight">{day.leave_type}</p>
              ) : day.worked_minutes > 0 ? (
                <p className="text-muted-foreground tabular-nums">{formatMinutes(day.worked_minutes)}</p>
              ) : null}
              {Number(day.timesheet_hours) > 0 ? (
                <p className="text-muted-foreground tabular-nums">{day.timesheet_hours}h booked</p>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {LEGEND.map((item) => (
          <span className="flex items-center gap-1.5" key={item.label}>
            <span className={cn('size-3 rounded-sm border', item.tone)} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

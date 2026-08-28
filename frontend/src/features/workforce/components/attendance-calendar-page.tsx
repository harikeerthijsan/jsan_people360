'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { AttendanceCalendar, formatMinutes } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useWorkforceCalendar } from '@/features/workforce/hooks';

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

/** One employee's month: attendance, leave, holidays and booked hours together. */
export function AttendanceCalendarPage(): React.JSX.Element {
  const now = React.useMemo(() => new Date(), []);
  const [employeeId, setEmployeeId] = React.useState('');
  const [year, setYear] = React.useState(now.getFullYear());
  const [month, setMonth] = React.useState(now.getMonth() + 1);

  const query = useWorkforceCalendar(employeeId || undefined, year, month);

  const step = (delta: number): void => {
    const next = month + delta;
    if (next < 1) {
      setMonth(12);
      setYear(year - 1);
    } else if (next > 12) {
      setMonth(1);
      setYear(year + 1);
    } else {
      setMonth(next);
    }
  };

  const days = query.data ?? [];
  const workedMinutes = days.reduce((sum, day) => sum + day.worked_minutes, 0);
  const bookedHours = days.reduce((sum, day) => sum + Number(day.timesheet_hours), 0);
  const leaveDays = days.filter((day) => day.leave_type).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance calendar"
        description="A month at a time, with leave and holidays in place rather than in a separate list."
      />

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />

          <div className="flex items-center gap-2">
            <Button
              aria-label="Previous month"
              onClick={() => {
                step(-1);
              }}
              size="icon"
              variant="outline"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="min-w-40 text-center font-medium">
              {MONTHS[month - 1]} {year}
            </span>
            <Button
              aria-label="Next month"
              onClick={() => {
                step(1);
              }}
              size="icon"
              variant="outline"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {!employeeId ? (
            <EmptyState title="Choose an employee" description="Pick someone above to see their month." />
          ) : query.isPending ? (
            <LoadingState />
          ) : query.error ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : (
            <AttendanceCalendar days={days} />
          )}
        </CardContent>
      </Card>

      {employeeId && !query.isPending && !query.error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">This month</CardTitle>
            <CardDescription>
              Hours worked come from attendance; hours booked come from timesheets. They are separate records,
              and a gap between them is worth looking at.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-muted-foreground text-sm">Worked</p>
              <p className="text-xl font-semibold tabular-nums">{formatMinutes(workedMinutes)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-sm">Booked on timesheets</p>
              <p className="text-xl font-semibold tabular-nums">{bookedHours.toFixed(2)}h</p>
            </div>
            <div>
              <p className="text-muted-foreground text-sm">Days on leave</p>
              <p className="text-xl font-semibold tabular-nums">{leaveDays}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

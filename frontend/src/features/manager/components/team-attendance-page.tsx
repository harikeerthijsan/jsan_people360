'use client';

import { useSearchParams } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { Tabs } from '@/components/common/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  TeamAttendanceBadge,
  TeamMemberCell,
  formatMinutes,
  formatTime,
} from '@/features/manager/components/widgets';
import { useTeam, useTeamAttendance } from '@/features/manager/hooks';
import {
  TEAM_ATTENDANCE_STATUSES,
  TEAM_ATTENDANCE_STATUS_LABELS,
  type TeamAttendanceRow,
} from '@/features/manager/types';

/**
 * Team Attendance.
 *
 * Read-only, and not by omission: there is no endpoint that edits a day from
 * here. A manager corrects attendance by approving the correction request the
 * employee raised, which is the flow the workforce module already has and the
 * only one that leaves a record of who asked for what.
 *
 * The window presets are computed in the browser and sent as explicit dates, so
 * "this week" means the same thing to the client and the server rather than
 * depending on where each of them thinks the week starts.
 */

type Window = 'today' | 'week' | 'month' | 'range';

const WINDOW_TABS = [
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'This week' },
  { id: 'month', label: 'This month' },
  { id: 'range', label: 'Date range' },
] as const;

function iso(value: Date): string {
  return value.toISOString().slice(0, 10);
}

/** The inclusive window a preset covers, as the API expects it. */
function windowFor(preset: Window): { from_date: string; to_date: string } | null {
  const today = new Date();
  if (preset === 'today') return { from_date: iso(today), to_date: iso(today) };

  if (preset === 'week') {
    const monday = new Date(today);
    // `getDay()` counts Sunday as 0; the week starts on Monday, as it does on a
    // timesheet and in a shift's weekly-off list.
    monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
    return { from_date: iso(monday), to_date: iso(today) };
  }

  if (preset === 'month') {
    return { from_date: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to_date: iso(today) };
  }
  return null;
}

export function TeamAttendancePage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [page, setPage] = React.useState(1);
  const [from, setFrom] = React.useState('');
  const [to, setTo] = React.useState('');
  const [employee, setEmployee] = React.useState('');
  const [status, setStatus] = React.useState('');

  // Read from the URL rather than mirrored into state. `Tabs` already writes the
  // selection there, and a second copy would need syncing back -- which means
  // setting state while a child renders.
  const requested = searchParams.get('window') ?? 'today';
  const preset = (WINDOW_TABS.some((tab) => tab.id === requested) ? requested : 'today') as Window;

  // A window change resets the page: page 3 of "this month" is very often past
  // the end of "today", and an empty table would read as missing data.
  React.useEffect(() => {
    setPage(1);
  }, [preset]);

  const roster = useTeam({ page_size: 100 });

  const params = React.useMemo(() => {
    const window =
      preset === 'range' ? (from && to ? { from_date: from, to_date: to } : null) : windowFor(preset);
    return {
      page,
      page_size: 20,
      ...(window ?? {}),
      ...(employee ? { employee_id: employee } : {}),
      ...(status ? { status } : {}),
    };
  }, [page, preset, from, to, employee, status]);

  const attendance = useTeamAttendance(params);

  const columns: DataTableColumn<TeamAttendanceRow>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    {
      id: 'date',
      header: 'Date',
      cell: (row) => <span className="tabular-nums">{row.record.attendance_date}</span>,
    },
    { id: 'in', header: 'Check in', cell: (row) => formatTime(row.record.check_in_at) },
    { id: 'out', header: 'Check out', cell: (row) => formatTime(row.record.check_out_at) },
    {
      id: 'hours',
      header: 'Working hours',
      align: 'right',
      cell: (row) => formatMinutes(row.record.worked_minutes),
    },
    { id: 'status', header: 'Status', cell: (row) => <TeamAttendanceBadge status={row.record.status} /> },
    { id: 'late', header: 'Late', align: 'right', cell: (row) => formatMinutes(row.record.late_minutes) },
    {
      id: 'early',
      header: 'Early exit',
      align: 'right',
      cell: (row) => formatMinutes(row.record.early_exit_minutes),
    },
    {
      id: 'overtime',
      header: 'Overtime',
      align: 'right',
      cell: (row) => formatMinutes(row.record.overtime_minutes),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Attendance"
        description="Your direct reports' register. Corrections are approved, never edited here."
      />

      <Tabs defaultTabId="today" label="Attendance window" paramName="window" tabs={[...WINDOW_TABS]}>
        {() => (
          <div className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              {preset === 'range' ? (
                <>
                  <input
                    aria-label="From date"
                    className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                    onChange={(event) => {
                      setFrom(event.target.value);
                      setPage(1);
                    }}
                    type="date"
                    value={from}
                  />
                  <input
                    aria-label="To date"
                    className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                    onChange={(event) => {
                      setTo(event.target.value);
                      setPage(1);
                    }}
                    type="date"
                    value={to}
                  />
                </>
              ) : null}

              <Select
                onValueChange={(next) => {
                  setEmployee(next === 'all' ? '' : next);
                  setPage(1);
                }}
                value={employee === '' ? 'all' : employee}
              >
                <SelectTrigger aria-label="Team member" className="w-full sm:w-56">
                  <SelectValue placeholder="Team member" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Everyone on my team</SelectItem>
                  {(roster.data?.items ?? []).map((member) => (
                    <SelectItem key={member.id} value={member.id}>
                      {member.full_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                onValueChange={(next) => {
                  setStatus(next === 'all' ? '' : next);
                  setPage(1);
                }}
                value={status === '' ? 'all' : status}
              >
                <SelectTrigger aria-label="Attendance status" className="w-full sm:w-44">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {TEAM_ATTENDANCE_STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {TEAM_ATTENDANCE_STATUS_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DataTable
              caption="Team attendance"
              columns={columns}
              emptyDescription="Nothing was recorded for your team in this window."
              emptyTitle="No attendance"
              error={attendance.error}
              getRowId={(row) => row.record.id}
              isLoading={attendance.isPending}
              onRetry={() => void attendance.refetch()}
              rows={attendance.data?.items ?? []}
            />

            {attendance.data ? (
              <Pagination itemLabel="days" meta={attendance.data.meta} onPageChange={setPage} />
            ) : null}
          </div>
        )}
      </Tabs>
    </div>
  );
}

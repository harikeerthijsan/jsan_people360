'use client';

import { Plus, Trash2 } from 'lucide-react';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Tabs } from '@/components/common/tabs';
import { TimesheetStatusBadge } from '@/components/common/workforce-widgets';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  useMyTimesheetWeek,
  useMyTimesheets,
  useSaveMyTimesheet,
  useSubmitMyTimesheet,
} from '@/features/self-service/hooks';
import { MAX_DAILY_HOURS, type MyTimesheetFormValues } from '@/features/self-service/schema';
import type { MyProject, Timesheet } from '@/features/self-service/types';

/**
 * My Timesheets.
 *
 * A grid, not a form-per-entry: a week is edited as a whole and saved as a
 * whole, which is also how the API models it. Rows are added and removed
 * locally and the week is posted in one request, so a half-saved week is not a
 * state that can exist.
 *
 * The project list comes from the same response as the week, and contains only
 * allocations that were live during it. Offering a project the save endpoint
 * would refuse is worse than offering none.
 */

interface DraftEntry {
  key: string;
  project_id: string;
  work_date: string;
  task: string;
  hours: string;
  billable: boolean;
  comments: string;
}

function isoDate(value: Date): string {
  return `${String(value.getFullYear())}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function weekDays(weekStart: string): string[] {
  const monday = new Date(`${weekStart}T00:00:00`);
  return Array.from({ length: 7 }, (_, offset) => {
    const day = new Date(monday);
    day.setDate(day.getDate() + offset);
    return isoDate(day);
  });
}

function shortDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
}

/** The Monday of the week containing `value`. */
function mondayOf(value: Date): string {
  const shifted = new Date(value);
  shifted.setDate(shifted.getDate() - ((shifted.getDay() + 6) % 7));
  return isoDate(shifted);
}

let nextKey = 0;

export function MyTimesheetsPage(): React.JSX.Element {
  const [weekStart, setWeekStart] = React.useState(() => mondayOf(new Date()));
  const week = useMyTimesheetWeek(weekStart);
  const history = useMyTimesheets();
  const save = useSaveMyTimesheet();
  const submit = useSubmitMyTimesheet();

  const [entries, setEntries] = React.useState<DraftEntry[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  // Reload the grid whenever the server's version of the week changes -- after a
  // save, after a submission, or when the week is switched. The draft is a view
  // of what was stored, not a parallel copy of it.
  const stored = week.data?.timesheet;
  React.useEffect(() => {
    setEntries(
      (stored?.entries ?? []).map((entry) => ({
        key: `stored-${entry.id}`,
        project_id: entry.project_id,
        work_date: entry.work_date,
        task: entry.task,
        hours: String(entry.hours),
        billable: entry.billable,
        comments: entry.comments ?? '',
      })),
    );
    setError(null);
  }, [stored]);

  const projects: MyProject[] = week.data?.projects.filter((project) => project.is_current) ?? [];
  const editable = week.data?.editable ?? false;
  const days = weekDays(weekStart);

  const totals = React.useMemo(() => {
    const perDay = new Map<string, number>();
    let total = 0;
    for (const entry of entries) {
      const hours = Number(entry.hours) || 0;
      perDay.set(entry.work_date, (perDay.get(entry.work_date) ?? 0) + hours);
      total += hours;
    }
    return { perDay, total };
  }, [entries]);

  const addRow = (): void => {
    nextKey += 1;
    setEntries((current) => [
      ...current,
      {
        key: `draft-${String(nextKey)}`,
        project_id: projects[0]?.project_id ?? '',
        work_date: days[0] ?? weekStart,
        task: '',
        hours: '',
        billable: true,
        comments: '',
      },
    ]);
  };

  const patchRow = (key: string, changes: Partial<DraftEntry>): void => {
    setEntries((current) => current.map((entry) => (entry.key === key ? { ...entry, ...changes } : entry)));
  };

  const removeRow = (key: string): void => {
    setEntries((current) => current.filter((entry) => entry.key !== key));
  };

  const persist = (): void => {
    const payload: MyTimesheetFormValues = {
      week_start_date: weekStart,
      entries: entries.map((entry) => ({
        project_id: entry.project_id,
        work_date: entry.work_date,
        task: entry.task,
        hours: entry.hours,
        billable: entry.billable,
        comments: entry.comments || undefined,
      })),
    };

    // Enough validation to catch a typo before a round trip; the server is
    // still the authority on the day total and on the allocation window.
    const incomplete = payload.entries.some(
      (entry) => !entry.project_id || !entry.task.trim() || !entry.hours,
    );
    if (incomplete) {
      setError('Every row needs a project, a task and hours.');
      return;
    }
    const overloaded = [...totals.perDay.entries()].find(([, hours]) => hours > MAX_DAILY_HOURS);
    if (overloaded) {
      setError(`${shortDay(overloaded[0])} totals more than ${String(MAX_DAILY_HOURS)} hours.`);
      return;
    }

    setError(null);
    save.mutate(payload);
  };

  const historyColumns: DataTableColumn<Timesheet>[] = [
    {
      id: 'code',
      header: 'Timesheet',
      cell: (row) => <span className="font-medium">{row.timesheet_code}</span>,
    },
    {
      id: 'week',
      header: 'Week beginning',
      cell: (row) => <span className="tabular-nums">{row.week_start_date}</span>,
    },
    {
      id: 'hours',
      header: 'Hours',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.total_hours}</span>,
    },
    {
      id: 'billable',
      header: 'Billable',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.billable_hours}</span>,
    },
    { id: 'status', header: 'Status', cell: (row) => <TimesheetStatusBadge status={row.status} /> },
    {
      id: 'notes',
      header: 'Decision',
      cell: (row) => <span className="text-muted-foreground line-clamp-2">{row.decision_notes ?? '—'}</span>,
    },
    {
      id: 'open',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button
          onClick={() => {
            setWeekStart(row.week_start_date);
          }}
          size="sm"
          variant="outline"
        >
          Open week
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Timesheets"
        description="A week is saved whole. Once submitted it is not edited unless it is returned to you."
        actions={
          <div className="flex items-center gap-2">
            <Input
              aria-label="Week beginning"
              className="w-40"
              onChange={(event) => {
                if (event.target.value) setWeekStart(mondayOf(new Date(`${event.target.value}T00:00:00`)));
              }}
              type="date"
              value={weekStart}
            />
          </div>
        }
      />

      {week.isPending ? (
        <LoadingState message="Loading your week…" />
      ) : (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-sm">Week beginning {weekStart}</CardTitle>
              <CardDescription>
                {stored
                  ? `${stored.timesheet_code} · ${stored.total_hours} hours booked`
                  : 'Nothing booked for this week yet.'}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {stored ? <TimesheetStatusBadge status={stored.status} /> : null}
              <Badge variant="outline">{totals.total.toFixed(2)} h</Badge>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {stored?.status === 'rejected' && stored.decision_notes ? (
              <p className="border-destructive/30 bg-destructive-subtle rounded-md border p-3 text-sm">
                <span className="font-medium">Returned for correction:</span> {stored.decision_notes}
              </p>
            ) : null}

            {!editable ? (
              <p className="text-muted-foreground text-sm">
                This week is {stored?.status ?? 'locked'} and can no longer be edited.
              </p>
            ) : null}

            {projects.length === 0 ? (
              <EmptyState
                description="Hours can only be booked against a project you are allocated to. Ask your manager to allocate you."
                title="No current allocations"
              />
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-3xl text-sm">
                    <thead>
                      <tr className="text-muted-foreground border-b text-left text-xs">
                        <th className="p-2 font-medium">Day</th>
                        <th className="p-2 font-medium">Project</th>
                        <th className="p-2 font-medium">Task</th>
                        <th className="p-2 text-right font-medium">Hours</th>
                        <th className="p-2 font-medium">Billable</th>
                        <th className="p-2 font-medium">Comments</th>
                        <th className="p-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((entry) => (
                        <tr className="border-b last:border-0" key={entry.key}>
                          <td className="p-2">
                            <Select
                              disabled={!editable}
                              onValueChange={(value) => {
                                patchRow(entry.key, { work_date: value });
                              }}
                              value={entry.work_date}
                            >
                              <SelectTrigger aria-label="Day" className="w-32">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {days.map((day) => (
                                  <SelectItem key={day} value={day}>
                                    {shortDay(day)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="p-2">
                            <Select
                              disabled={!editable}
                              onValueChange={(value) => {
                                patchRow(entry.key, { project_id: value });
                              }}
                              value={entry.project_id}
                            >
                              <SelectTrigger aria-label="Project" className="w-52">
                                <SelectValue placeholder="Choose a project" />
                              </SelectTrigger>
                              <SelectContent>
                                {projects.map((project) => (
                                  <SelectItem key={project.project_id} value={project.project_id}>
                                    {project.project_name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="p-2">
                            <Input
                              aria-label="Task"
                              disabled={!editable}
                              onChange={(event) => {
                                patchRow(entry.key, { task: event.target.value });
                              }}
                              placeholder="What you worked on"
                              value={entry.task}
                            />
                          </td>
                          <td className="p-2">
                            <Input
                              aria-label="Hours"
                              className="w-24 text-right tabular-nums"
                              disabled={!editable}
                              inputMode="decimal"
                              onChange={(event) => {
                                patchRow(entry.key, { hours: event.target.value });
                              }}
                              placeholder="0.00"
                              value={entry.hours}
                            />
                          </td>
                          <td className="p-2">
                            <input
                              aria-label="Billable"
                              checked={entry.billable}
                              className="size-4"
                              disabled={!editable}
                              onChange={(event) => {
                                patchRow(entry.key, { billable: event.target.checked });
                              }}
                              type="checkbox"
                            />
                          </td>
                          <td className="p-2">
                            <Input
                              aria-label="Comments"
                              disabled={!editable}
                              onChange={(event) => {
                                patchRow(entry.key, { comments: event.target.value });
                              }}
                              value={entry.comments}
                            />
                          </td>
                          <td className="p-2 text-right">
                            <Button
                              aria-label="Remove this row"
                              disabled={!editable}
                              onClick={() => {
                                removeRow(entry.key);
                              }}
                              size="sm"
                              variant="ghost"
                            >
                              <Trash2 className="size-4" aria-hidden="true" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {entries.length === 0 ? (
                        <tr>
                          <td className="text-muted-foreground p-4 text-center" colSpan={7}>
                            No entries yet.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>

                <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums">
                  {days.map((day) => (
                    <span key={day}>
                      {shortDay(day)}: {(totals.perDay.get(day) ?? 0).toFixed(2)} h
                    </span>
                  ))}
                </div>

                {error ? <p className="text-destructive text-sm">{error}</p> : null}

                <div className="flex flex-wrap gap-2">
                  <Button disabled={!editable} onClick={addRow} size="sm" variant="outline">
                    <Plus className="size-4" aria-hidden="true" />
                    Add a row
                  </Button>
                  <Button disabled={!editable} isLoading={save.isPending} onClick={persist} size="sm">
                    Save draft
                  </Button>
                  <Button
                    disabled={!stored || stored.status === 'submitted' || stored.status === 'approved'}
                    isLoading={submit.isPending}
                    onClick={() => {
                      if (stored) submit.mutate(stored.id);
                    }}
                    size="sm"
                    variant="secondary"
                  >
                    Submit for approval
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">History</h2>
        <Tabs label="Timesheet history" paramName="tab" tabs={[{ id: 'all', label: 'All weeks' }]}>
          {() => (
            <DataTable
              columns={historyColumns}
              emptyDescription="You have not filed a timesheet yet."
              emptyTitle="No timesheets"
              error={history.error}
              getRowId={(row) => row.id}
              isLoading={history.isPending}
              onRetry={() => void history.refetch()}
              rows={history.data?.items ?? []}
            />
          )}
        </Tabs>
      </section>
    </div>
  );
}

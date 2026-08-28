'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCompleteTeamTask,
  useDecideResignation,
  useSaveHandover,
  useTeamOffboardingCases,
  useTeamResignations,
} from '@/features/offboarding/hooks';
import {
  RESIGNATION_STATUS_LABELS,
  TASK_STATUS_LABELS,
  type HandoverStatus,
  type OffboardingCase,
  type ResignationRead,
} from '@/features/offboarding/types';

/**
 * Manager offboarding.
 *
 * Direct reports only, and that is the server's doing rather than this
 * component's -- the endpoints behind it take no manager id and resolve the
 * team from the session. Nothing here filters a longer list down to the team.
 *
 * A manager sees two things: resignations awaiting their decision, and the
 * handover they owe for anyone already leaving. Everything else on a case --
 * assets, access, settlement -- belongs to another department and is not shown.
 */

export function ManagerOffboardingPage(): React.JSX.Element {
  const resignations = useTeamResignations();
  const cases = useTeamOffboardingCases();
  const decide = useDecideResignation();

  const [selected, setSelected] = React.useState<OffboardingCase | null>(null);

  const pending = (resignations.data?.items ?? []).filter((row) => row.status === 'manager_review');
  const active = cases.data?.items ?? [];

  const columns: DataTableColumn<ResignationRead>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => row.employee.full_name },
    { id: 'code', header: 'Reference', cell: (row) => row.resignation_code },
    { id: 'date', header: 'Resigned on', cell: (row) => row.resignation_date },
    { id: 'proposed', header: 'Proposed last day', cell: (row) => row.proposed_last_working_day },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="outline">{RESIGNATION_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) =>
        row.status === 'manager_review' ? (
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              onClick={() => decide.mutate({ id: row.id, payload: { decision: 'approve' } })}
              disabled={decide.isPending}
            >
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => decide.mutate({ id: row.id, payload: { decision: 'reject' } })}
              disabled={decide.isPending}
            >
              Reject
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team offboarding"
        description="Resignations and handovers for the people who report to you."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Awaiting your decision" value={pending.length} />
        <StatCard label="Serving notice" value={active.length} />
        <StatCard
          label="Handovers outstanding"
          value={active.filter((row) => row.handover?.status !== 'completed').length}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Resignations</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={resignations.data?.items ?? []}
            columns={columns}
            getRowId={(row) => row.id}
            isLoading={resignations.isLoading}
            emptyTitle="No resignations"
            emptyDescription="Nobody on your team has resigned."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Handover and my tasks</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {active.length === 0 ? (
            <p className="text-muted-foreground text-sm">No offboarding in progress on your team.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {active.map((row) => (
                <Button
                  key={row.id}
                  size="sm"
                  variant={selected?.id === row.id ? 'default' : 'outline'}
                  onClick={() => setSelected(row)}
                >
                  {row.employee.full_name} — {row.last_working_day}
                </Button>
              ))}
            </div>
          )}
          {selected ? <HandoverPanel offboardingCase={selected} /> : null}
        </CardContent>
      </Card>
    </div>
  );
}

function HandoverPanel({ offboardingCase }: { offboardingCase: OffboardingCase }): React.JSX.Element {
  const save = useSaveHandover();
  const completeTask = useCompleteTeamTask();

  const handover = offboardingCase.handover;
  const [status, setStatus] = React.useState<HandoverStatus>(handover?.status ?? 'in_progress');
  const [projects, setProjects] = React.useState(handover?.projects ?? '');
  const [responsibilities, setResponsibilities] = React.useState(handover?.responsibilities ?? '');
  const [documentation, setDocumentation] = React.useState(handover?.documentation ?? '');
  const [notes, setNotes] = React.useState(handover?.notes ?? '');

  const myTasks = offboardingCase.tasks.filter((task) => task.department === 'manager');

  return (
    <div className="grid gap-6 border-t pt-4 lg:grid-cols-2">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({
            caseId: offboardingCase.id,
            payload: { status, projects, responsibilities, documentation, notes },
          });
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="handover-status">Handover status</Label>
          <select
            id="handover-status"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={status}
            onChange={(event) => setStatus(event.target.value as HandoverStatus)}
          >
            <option value="not_started">Not started</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="projects">Projects</Label>
          <Input id="projects" value={projects} onChange={(event) => setProjects(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="responsibilities">Responsibilities</Label>
          <Textarea
            id="responsibilities"
            rows={2}
            value={responsibilities}
            onChange={(event) => setResponsibilities(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="documentation">Documentation</Label>
          <Textarea
            id="documentation"
            rows={2}
            value={documentation}
            onChange={(event) => setDocumentation(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="notes">Notes</Label>
          <Textarea id="notes" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </div>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save handover'}
        </Button>
      </form>

      <div className="space-y-3">
        <p className="text-sm font-medium">My checklist</p>
        {myTasks.length === 0 ? (
          <EmptyState title="No tasks" description="Nothing on this case is assigned to you." />
        ) : (
          <ul className="space-y-2">
            {myTasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between gap-4 text-sm">
                <div>
                  <p>{task.title}</p>
                  <p className="text-muted-foreground text-xs">Due {task.due_date}</p>
                </div>
                {task.status === 'completed' ? (
                  <Badge variant="secondary">{TASK_STATUS_LABELS[task.status]}</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => completeTask.mutate({ taskId: task.id, status: 'completed' })}
                    disabled={completeTask.isPending}
                  >
                    Mark done
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

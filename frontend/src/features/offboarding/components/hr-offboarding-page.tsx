'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  useCompleteOffboarding,
  useGenerateExitDocument,
  useOffboardingCases,
  useOffboardingSummary,
  useProcessResignation,
  useResignations,
  useUpdateAccess,
  useUpdateAsset,
  useUpdateCaseTask,
  useUpdateSettlement,
} from '@/features/offboarding/hooks';
import {
  DEPARTMENT_LABELS,
  EXIT_DOCUMENT_LABELS,
  RESIGNATION_STATUS_LABELS,
  SETTLEMENT_STATUS_LABELS,
  TASK_STATUS_LABELS,
  type OffboardingCase,
  type ResignationRead,
  type SettlementStatus,
} from '@/features/offboarding/types';

/**
 * HR offboarding.
 *
 * What HR sees is what their permissions allow, and the server decides that --
 * a screen that hid a button would still have been an endpoint somebody could
 * call. Anything an HR Executive lacks the permission for returns 403 and the
 * toast says so.
 *
 * The two administrative acts are deliberately separate from the rest of the
 * page: settling a last working day and completing an offboarding are the two
 * that change what an employee can still do, and both are audited.
 */

export function HrOffboardingPage(): React.JSX.Element {
  const summary = useOffboardingSummary();
  const resignations = useResignations();
  const cases = useOffboardingCases();
  const process = useProcessResignation();

  const [selected, setSelected] = React.useState<OffboardingCase | null>(null);
  const [lastDay, setLastDay] = React.useState('');

  const stats = summary.data;

  const resignationColumns: DataTableColumn<ResignationRead>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => row.employee.full_name },
    { id: 'code', header: 'Reference', cell: (row) => row.resignation_code },
    { id: 'resigned', header: 'Resigned on', cell: (row) => row.resignation_date },
    {
      id: 'notice',
      header: 'Notice',
      cell: (row) => (
        <span className="tabular-nums">
          {row.notice_period_days} days{row.notice_period_adjusted ? ' (adjusted)' : ''}
        </span>
      ),
    },
    {
      id: 'lastDay',
      header: 'Last working day',
      cell: (row) => row.approved_last_working_day ?? row.proposed_last_working_day,
    },
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
        row.status === 'hr_review' ? (
          <Button
            size="sm"
            onClick={() =>
              process.mutate({
                id: row.id,
                payload: {
                  approved_last_working_day:
                    lastDay || row.recommended_last_working_day || row.proposed_last_working_day,
                },
              })
            }
            disabled={process.isPending}
          >
            Process
          </Button>
        ) : null,
    },
  ];

  const caseColumns: DataTableColumn<OffboardingCase>[] = [
    { id: 'case', header: 'Case', cell: (row) => row.case_code },
    { id: 'employee', header: 'Employee', cell: (row) => row.employee.full_name },
    { id: 'lastDay', header: 'Last working day', cell: (row) => row.last_working_day },
    {
      id: 'clearance',
      header: 'Clearance',
      cell: (row) => <span className="tabular-nums">{row.progress_percent}%</span>,
    },
    {
      id: 'interview',
      header: 'Exit interview',
      cell: (row) => (
        <Badge variant={row.exit_interview_submitted ? 'secondary' : 'outline'}>
          {row.exit_interview_submitted ? 'Submitted' : 'Pending'}
        </Badge>
      ),
    },
    {
      id: 'settlement',
      header: 'Settlement',
      cell: (row) => (
        <Badge variant="outline">
          {row.settlement ? SETTLEMENT_STATUS_LABELS[row.settlement.status] : 'Not started'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button size="sm" variant="outline" onClick={() => setSelected(row)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Offboarding"
        description="Resignations, notice periods, clearance, exit interviews and settlement tracking."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Active resignations" value={stats?.active_resignations ?? 0} />
        <StatCard label="Awaiting HR" value={stats?.pending_hr_review ?? 0} />
        <StatCard label="Serving notice" value={stats?.serving_notice ?? 0} />
        <StatCard label="Exiting this month" value={stats?.exiting_this_month ?? 0} />
        <StatCard label="Pending clearance" value={stats?.pending_clearance ?? 0} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Resignations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex max-w-xs flex-col gap-2">
            <Label htmlFor="last-day">Last working day to apply when processing</Label>
            <Input
              id="last-day"
              type="date"
              value={lastDay}
              onChange={(event) => setLastDay(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              Leave blank to accept the manager&apos;s recommendation, then the employee&apos;s proposal.
            </p>
          </div>
          <DataTable
            rows={resignations.data?.items ?? []}
            columns={resignationColumns}
            getRowId={(row) => row.id}
            isLoading={resignations.isLoading}
            emptyTitle="No resignations"
            emptyDescription="Nothing to review."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Offboarding cases</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={cases.data?.items ?? []}
            columns={caseColumns}
            getRowId={(row) => row.id}
            isLoading={cases.isLoading}
            emptyTitle="No cases"
            emptyDescription="No offboarding in progress."
          />
        </CardContent>
      </Card>

      {selected ? <CasePanel offboardingCase={selected} /> : null}
    </div>
  );
}

function CasePanel({ offboardingCase }: { offboardingCase: OffboardingCase }): React.JSX.Element {
  const updateTask = useUpdateCaseTask();
  const updateAsset = useUpdateAsset();
  const updateAccess = useUpdateAccess();
  const updateSettlement = useUpdateSettlement();
  const generate = useGenerateExitDocument();
  const complete = useCompleteOffboarding();

  const [settlementStatus, setSettlementStatus] = React.useState<SettlementStatus>(
    offboardingCase.settlement?.status ?? 'not_started',
  );
  const [reference, setReference] = React.useState(offboardingCase.settlement?.settlement_reference ?? '');

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {offboardingCase.case_code} — {offboardingCase.employee.full_name}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <p className="text-sm font-medium">Checklist</p>
          <ul className="space-y-2">
            {offboardingCase.tasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between gap-3 text-sm">
                <div>
                  <p>{task.title}</p>
                  <p className="text-muted-foreground text-xs">
                    {DEPARTMENT_LABELS[task.department]} · due {task.due_date}
                  </p>
                </div>
                {task.status === 'completed' || task.status === 'waived' ? (
                  <Badge variant="secondary">{TASK_STATUS_LABELS[task.status]}</Badge>
                ) : (
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => updateTask.mutate({ taskId: task.id, status: 'completed' })}
                    >
                      Done
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => updateTask.mutate({ taskId: task.id, status: 'waived' })}
                    >
                      Waive
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="space-y-6">
          <div className="space-y-3">
            <p className="text-sm font-medium">Assets</p>
            <ul className="space-y-2">
              {offboardingCase.assets.map((asset) => (
                <li key={asset.id} className="flex items-center justify-between gap-3 text-sm">
                  <span>{asset.asset_name}</span>
                  {asset.status === 'assigned' ? (
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => updateAsset.mutate({ assetId: asset.id, status: 'returned' })}
                      >
                        Returned
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => updateAsset.mutate({ assetId: asset.id, status: 'waived' })}
                      >
                        N/A
                      </Button>
                    </div>
                  ) : (
                    <Badge variant="secondary">{asset.status}</Badge>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-3">
            <p className="text-sm font-medium">Access</p>
            <ul className="space-y-2">
              {offboardingCase.access_items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 text-sm">
                  <span>{item.system_name}</span>
                  {item.status === 'pending' ? (
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => updateAccess.mutate({ itemId: item.id, status: 'revoked' })}
                      >
                        Revoked
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => updateAccess.mutate({ itemId: item.id, status: 'not_applicable' })}
                      >
                        N/A
                      </Button>
                    </div>
                  ) : (
                    <Badge variant="secondary">{item.status}</Badge>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="space-y-3">
          <p className="text-sm font-medium">Full &amp; final settlement</p>
          <p className="text-muted-foreground text-xs">Status tracking only. No amount is calculated here.</p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="settlement-status">Status</Label>
              <select
                id="settlement-status"
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={settlementStatus}
                onChange={(event) => setSettlementStatus(event.target.value as SettlementStatus)}
              >
                {Object.entries(SETTLEMENT_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="settlement-reference">Reference</Label>
              <Input
                id="settlement-reference"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            </div>
            <Button
              size="sm"
              onClick={() =>
                updateSettlement.mutate({
                  caseId: offboardingCase.id,
                  status: settlementStatus,
                  reference,
                })
              }
            >
              Save
            </Button>
          </div>
        </section>

        <section className="space-y-3">
          <p className="text-sm font-medium">Exit documents</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(EXIT_DOCUMENT_LABELS).map(([value, label]) => (
              <Button
                key={value}
                size="sm"
                variant="outline"
                onClick={() =>
                  generate.mutate({
                    caseId: offboardingCase.id,
                    documentType: value as keyof typeof EXIT_DOCUMENT_LABELS,
                    release: true,
                  })
                }
                disabled={generate.isPending}
              >
                Generate {label.toLowerCase()}
              </Button>
            ))}
          </div>

          <div className="border-t pt-4">
            <Button
              variant="destructive"
              size="sm"
              onClick={() =>
                complete.mutate({
                  caseId: offboardingCase.id,
                  comments: null,
                  force: offboardingCase.progress_percent < 100,
                })
              }
              disabled={complete.isPending || offboardingCase.status === 'completed'}
            >
              {offboardingCase.status === 'completed' ? 'Completed' : 'Complete offboarding'}
            </Button>
            <p className="text-muted-foreground mt-2 text-xs">
              Sets the employee inactive and ends their allocations. Historical records are kept. Completing
              with outstanding clearance is recorded as an override.
            </p>
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

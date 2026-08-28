'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { routes } from '@/config/site';
import {
  useAddReviewComment,
  useCancelAdjustment,
  useCompleteReview,
  useCreateAdjustment,
  useMarkRecord,
  usePayrollRun,
  usePayrollRunRecords,
  useResolveException,
  useReviewChecklist,
  useReviewComments,
  useReviewReadiness,
  useRunAdjustments,
  useRunExceptions,
  useUpdateChecklistItem,
} from '@/features/payroll/hooks';
import {
  ADJUSTMENT_STATUS_LABELS,
  COMPONENT_TYPE_LABELS,
  EXCEPTION_SEVERITY_LABELS,
  EXCEPTION_TYPE_LABELS,
  RECORD_STATUS_LABELS,
  RUN_STATUS_LABELS,
  formatMoney,
  type PayrollAdjustment,
  type PayrollExceptionSeverity,
  type PayrollRecord,
  type PayrollRunException,
} from '@/features/payroll/types';

/**
 * One run's review: exceptions to resolve, records to judge, adjustments to
 * layer on top of the calculation, the checklist, and completion.
 *
 * The rules the backend enforces are stated here rather than hidden:
 * exceptions are resolved with a reason and never deleted; adjustments are
 * additive, reasoned, and cancelled rather than removed; and "Review
 * complete" stays shut until every gate the readiness panel lists is met.
 * The buttons are conveniences — the server refuses regardless.
 */

const SEVERITY_VARIANT: Record<PayrollExceptionSeverity, 'destructive' | 'secondary' | 'outline'> = {
  critical: 'destructive',
  error: 'secondary',
  warning: 'outline',
};

export function PayrollRunReviewPage({ runId }: { runId: string }): React.JSX.Element {
  const runQuery = usePayrollRun(runId);
  const readiness = useReviewReadiness(runId);
  const exceptions = useRunExceptions(runId);
  const records = usePayrollRunRecords(runId, { page_size: 200 });
  const adjustments = useRunAdjustments(runId);
  const checklist = useReviewChecklist(runId);
  const comments = useReviewComments(runId);

  const resolve = useResolveException();
  const createAdjustment = useCreateAdjustment();
  const cancelAdjustment = useCancelAdjustment();
  const markRecord = useMarkRecord();
  const updateChecklist = useUpdateChecklistItem();
  const complete = useCompleteReview();
  const addComment = useAddReviewComment();

  const [resolving, setResolving] = React.useState<PayrollRunException | null>(null);
  const [resolution, setResolution] = React.useState('');
  const [resolutionNotes, setResolutionNotes] = React.useState('');

  const [adjusting, setAdjusting] = React.useState<PayrollRecord | null>(null);
  const [adjustmentForm, setAdjustmentForm] = React.useState({
    item_type: 'earning' as 'earning' | 'deduction',
    name: '',
    amount: '',
    reason: '',
  });

  const [cancelling, setCancelling] = React.useState<PayrollAdjustment | null>(null);
  const [cancelReason, setCancelReason] = React.useState('');

  const [completing, setCompleting] = React.useState(false);
  const [newComment, setNewComment] = React.useState('');

  if (runQuery.isPending) return <LoadingState />;
  if (runQuery.error) return <ErrorState error={runQuery.error} />;
  const run = runQuery.data;
  const ready = readiness.data;

  const exceptionColumns: DataTableColumn<PayrollRunException>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.employee.full_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.employee.employee_code}</div>
        </div>
      ),
    },
    {
      id: 'issue',
      header: 'Issue',
      cell: (row) => (
        <div className="max-w-lg">
          <div className="flex items-center gap-2">
            <Badge variant={SEVERITY_VARIANT[row.severity]}>
              {EXCEPTION_SEVERITY_LABELS[row.severity]}
            </Badge>
            <span className="text-sm font-medium">{EXCEPTION_TYPE_LABELS[row.exception_type]}</span>
          </div>
          <div className="text-muted-foreground mt-1 text-xs">{row.description}</div>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Resolution',
      cell: (row) =>
        row.status === 'resolved' ? (
          <div className="max-w-sm text-sm">
            <div>{row.resolution}</div>
            <div className="text-muted-foreground text-xs">
              by {row.resolved_by_name ?? 'unknown'}
              {row.resolved_at ? ` · ${new Date(row.resolved_at).toLocaleString()}` : ''}
            </div>
          </div>
        ) : (
          <Badge variant="outline">Open</Badge>
        ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) =>
        row.status === 'open' ? (
          <Can permission="payroll:exception_resolve">
            <Button size="sm" variant="outline" onClick={() => setResolving(row)}>
              Resolve
            </Button>
          </Can>
        ) : null,
    },
  ];

  const recordColumns: DataTableColumn<PayrollRecord>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.employee.full_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.employee.employee_code}</div>
        </div>
      ),
    },
    {
      id: 'net',
      header: 'Final net',
      cell: (row) => (
        <div>
          <div>{formatMoney(row.final_net, row.currency)}</div>
          {row.final_net !== row.net_pay ? (
            <div className="text-muted-foreground text-xs">
              orig {formatMoney(row.net_pay, row.currency)}
            </div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="space-y-1">
          <Badge
            variant={
              row.status === 'requires_review' || row.status === 'adjustment_required'
                ? 'destructive'
                : row.status === 'excluded'
                  ? 'outline'
                  : 'secondary'
            }
          >
            {RECORD_STATUS_LABELS[row.status]}
          </Badge>
          {row.exception_reason ? (
            <div className="text-muted-foreground max-w-md text-xs">{row.exception_reason}</div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => {
        const markable = ['calculated', 'reviewed', 'adjustment_required'].includes(row.status);
        return (
          <div className="flex justify-end gap-2">
            <Button asChild size="sm" variant="ghost">
              <Link href={routes.payrollRunEmployee(runId, row.employee.id)}>Open</Link>
            </Button>
            {row.status !== 'excluded' ? (
              <Can permission="payroll:adjustment_create">
                <Button size="sm" variant="outline" onClick={() => setAdjusting(row)}>
                  Adjust
                </Button>
              </Can>
            ) : null}
            {markable ? (
              <Can permission="payroll:review_complete">
                {row.status !== 'reviewed' ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      markRecord.mutate({ runId, employeeId: row.employee.id, status: 'reviewed' })
                    }
                  >
                    Mark reviewed
                  </Button>
                ) : null}
                {row.status !== 'adjustment_required' ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      markRecord.mutate({
                        runId,
                        employeeId: row.employee.id,
                        status: 'adjustment_required',
                      })
                    }
                  >
                    Needs adjustment
                  </Button>
                ) : null}
              </Can>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Review · ${run.period.name}`}
        description={`${run.run_code}. Exceptions are resolved with a reason, never deleted; adjustments add on top of the calculation, never edit it.`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={routes.payrollRunDetail(runId)}>Run summary</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={routes.payrollRunReconciliation(runId)}>Reconciliation</Link>
            </Button>
            <Can permission="payroll:review_complete">
              <Button
                disabled={!ready?.can_complete || run.status === 'review_complete'}
                isLoading={complete.isPending}
                onClick={() => setCompleting(true)}
              >
                {run.status === 'review_complete' ? 'Review complete' : 'Complete review'}
              </Button>
            </Can>
          </div>
        }
      />

      <div className="flex items-center gap-2">
        <Badge variant={run.status === 'requires_review' ? 'destructive' : 'secondary'}>
          {RUN_STATUS_LABELS[run.status]}
        </Badge>
      </div>

      {ready && !ready.can_complete ? (
        <Card>
          <CardHeader>
            <CardTitle>Before the review can complete</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <ul className="list-disc space-y-1 pl-5">
              {ready.open_critical_exceptions > 0 ? (
                <li>
                  {ready.open_critical_exceptions} critical exception
                  {ready.open_critical_exceptions === 1 ? '' : 's'} still open.
                </li>
              ) : null}
              {ready.records_requiring_review > 0 ? (
                <li>
                  {ready.records_requiring_review} record
                  {ready.records_requiring_review === 1 ? '' : 's'} the engine refused — fix the
                  cause and recalculate.
                </li>
              ) : null}
              {ready.records_adjustment_required > 0 ? (
                <li>
                  {ready.records_adjustment_required} record
                  {ready.records_adjustment_required === 1 ? '' : 's'} marked as needing an
                  adjustment.
                </li>
              ) : null}
              {ready.incomplete_checklist_items.length > 0 ? (
                <li>Checklist items open: {ready.incomplete_checklist_items.join(', ')}.</li>
              ) : null}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Exceptions</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              rows={exceptions.data ?? []}
              columns={exceptionColumns}
              getRowId={(row) => row.id}
              isLoading={exceptions.isLoading}
              error={exceptions.error}
              emptyTitle="No exceptions"
              emptyDescription="The engine raised nothing for this run."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Review checklist</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(checklist.data ?? []).map((item) => (
              <div key={item.item_key} className="flex items-start gap-2 text-sm">
                <Can
                  permission="payroll:review_complete"
                  fallback={
                    <Checkbox checked={item.completed} disabled aria-label={item.label} />
                  }
                >
                  <Checkbox
                    checked={item.completed}
                    aria-label={item.label}
                    disabled={updateChecklist.isPending}
                    onCheckedChange={(checked) =>
                      updateChecklist.mutate({
                        runId,
                        itemKey: item.item_key,
                        completed: checked === true,
                      })
                    }
                  />
                </Can>
                <div>
                  <div>{item.label}</div>
                  {item.completed && item.completed_by_name ? (
                    <div className="text-muted-foreground text-xs">
                      {item.completed_by_name}
                      {item.completed_at ? ` · ${new Date(item.completed_at).toLocaleString()}` : ''}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Employee records</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={records.data?.items ?? []}
            columns={recordColumns}
            getRowId={(row) => row.id}
            isLoading={records.isLoading}
            error={records.error}
            emptyTitle="No records"
            emptyDescription="Calculate the run first."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Adjustment history</CardTitle>
        </CardHeader>
        <CardContent>
          {(adjustments.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-sm">No adjustments on this run.</p>
          ) : (
            (adjustments.data ?? []).map((adjustment) => (
              <div
                key={adjustment.id}
                className="flex items-start justify-between gap-4 border-b py-2 text-sm"
              >
                <div>
                  <div className="font-medium">
                    {adjustment.employee.full_name} · {adjustment.name}
                    <Badge
                      className="ml-2"
                      variant={adjustment.status === 'active' ? 'secondary' : 'outline'}
                    >
                      {ADJUSTMENT_STATUS_LABELS[adjustment.status]}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {COMPONENT_TYPE_LABELS[adjustment.item_type]} · {adjustment.reason} · net{' '}
                    {formatMoney(adjustment.previous_net, run.currency)} →{' '}
                    {formatMoney(adjustment.new_net, run.currency)}
                  </div>
                  {adjustment.cancel_reason ? (
                    <div className="text-muted-foreground text-xs">
                      Cancelled: {adjustment.cancel_reason}
                    </div>
                  ) : null}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={adjustment.status === 'cancelled' ? 'line-through opacity-60' : ''}
                  >
                    {formatMoney(adjustment.amount, run.currency)}
                  </span>
                  {adjustment.status === 'active' ? (
                    <Can permission="payroll:adjustment_update">
                      <Button size="sm" variant="outline" onClick={() => setCancelling(adjustment)}>
                        Cancel
                      </Button>
                    </Can>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Review comments</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {(comments.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-sm">No comments yet.</p>
          ) : (
            (comments.data ?? []).map((comment) => (
              <div key={comment.id} className="border-b pb-2 text-sm">
                <div className="text-muted-foreground text-xs">
                  {comment.author_name ?? 'Unknown'} ·{' '}
                  {new Date(comment.created_at).toLocaleString()}
                  {comment.employee ? ` · on ${comment.employee.full_name}` : ''}
                </div>
                <div>{comment.comment}</div>
              </div>
            ))
          )}
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label htmlFor="review-comment">Add a comment</Label>
              <Textarea
                id="review-comment"
                rows={2}
                value={newComment}
                onChange={(event) => setNewComment(event.target.value)}
                placeholder="Comments are append-only — part of the review record."
              />
            </div>
            <Button
              disabled={!newComment.trim()}
              isLoading={addComment.isPending}
              onClick={() =>
                addComment.mutate(
                  { runId, comment: newComment.trim() },
                  { onSuccess: () => setNewComment('') },
                )
              }
            >
              Comment
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* -- Resolve exception ------------------------------------------- */}
      <Modal
        open={resolving !== null}
        onOpenChange={(open) => {
          if (!open) {
            setResolving(null);
            setResolution('');
            setResolutionNotes('');
          }
        }}
        title="Resolve exception"
        description={resolving ? resolving.description : ''}
        confirmLabel="Resolve"
        isConfirming={resolve.isPending}
        onConfirm={() => {
          if (!resolving) return;
          resolve.mutate(
            {
              runId,
              exceptionId: resolving.id,
              resolution: resolution.trim(),
              notes: resolutionNotes.trim() || null,
            },
            {
              onSuccess: () => {
                setResolving(null);
                setResolution('');
                setResolutionNotes('');
              },
            },
          );
        }}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="resolution">How was it resolved?</Label>
            <Input
              id="resolution"
              value={resolution}
              onChange={(event) => setResolution(event.target.value)}
              placeholder="e.g. Verified with HR — contractor paid off-cycle"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="resolution-notes">Notes (optional)</Label>
            <Textarea
              id="resolution-notes"
              rows={2}
              value={resolutionNotes}
              onChange={(event) => setResolutionNotes(event.target.value)}
            />
          </div>
          <p className="text-muted-foreground text-xs">
            The exception stays on record as resolved — nothing is deleted, and no attendance or
            leave data is touched from here.
          </p>
        </div>
      </Modal>

      {/* -- Add adjustment ---------------------------------------------- */}
      <Modal
        open={adjusting !== null}
        onOpenChange={(open) => {
          if (!open) {
            setAdjusting(null);
            setAdjustmentForm({ item_type: 'earning', name: '', amount: '', reason: '' });
          }
        }}
        title={adjusting ? `Adjust ${adjusting.employee.full_name}` : 'Adjust'}
        description="Additive only: a positive amount layered on the calculation. The original amounts stay untouched and traceable."
        confirmLabel="Add adjustment"
        isConfirming={createAdjustment.isPending}
        onConfirm={() => {
          if (!adjusting) return;
          createAdjustment.mutate(
            {
              runId,
              employeeId: adjusting.employee.id,
              payload: {
                item_type: adjustmentForm.item_type,
                name: adjustmentForm.name.trim(),
                amount: adjustmentForm.amount.trim(),
                reason: adjustmentForm.reason.trim(),
              },
            },
            {
              onSuccess: () => {
                setAdjusting(null);
                setAdjustmentForm({ item_type: 'earning', name: '', amount: '', reason: '' });
              },
            },
          );
        }}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="adjustment-type">Type</Label>
            <select
              id="adjustment-type"
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={adjustmentForm.item_type}
              onChange={(event) =>
                setAdjustmentForm((form) => ({
                  ...form,
                  item_type: event.target.value as 'earning' | 'deduction',
                }))
              }
            >
              <option value="earning">Additional earning (bonus, arrears, missed amount)</option>
              <option value="deduction">Additional deduction (recovery)</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="adjustment-name">Name</Label>
            <Input
              id="adjustment-name"
              value={adjustmentForm.name}
              onChange={(event) =>
                setAdjustmentForm((form) => ({ ...form, name: event.target.value }))
              }
              placeholder="e.g. Performance bonus"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="adjustment-amount">Amount</Label>
            <Input
              id="adjustment-amount"
              inputMode="decimal"
              value={adjustmentForm.amount}
              onChange={(event) =>
                setAdjustmentForm((form) => ({ ...form, amount: event.target.value }))
              }
              placeholder="A positive amount, e.g. 1000.00"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="adjustment-reason">Reason (required)</Label>
            <Textarea
              id="adjustment-reason"
              rows={2}
              value={adjustmentForm.reason}
              onChange={(event) =>
                setAdjustmentForm((form) => ({ ...form, reason: event.target.value }))
              }
            />
          </div>
        </div>
      </Modal>

      {/* -- Cancel adjustment ------------------------------------------- */}
      <Modal
        open={cancelling !== null}
        onOpenChange={(open) => {
          if (!open) {
            setCancelling(null);
            setCancelReason('');
          }
        }}
        title={cancelling ? `Cancel "${cancelling.name}"?` : 'Cancel adjustment'}
        description="The adjustment is marked cancelled and stays in the history with your reason; its amount is backed out of the employee's final pay."
        confirmLabel="Cancel adjustment"
        confirmVariant="destructive"
        isConfirming={cancelAdjustment.isPending}
        onConfirm={() => {
          if (!cancelling) return;
          cancelAdjustment.mutate(
            { runId, adjustmentId: cancelling.id, reason: cancelReason.trim() },
            {
              onSuccess: () => {
                setCancelling(null);
                setCancelReason('');
              },
            },
          );
        }}
      >
        <div className="space-y-1">
          <Label htmlFor="cancel-reason">Why is it cancelled?</Label>
          <Textarea
            id="cancel-reason"
            rows={2}
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value)}
          />
        </div>
      </Modal>

      {/* -- Complete review --------------------------------------------- */}
      <Modal
        open={completing}
        onOpenChange={setCompleting}
        title={`Complete the review of ${run.period.name}?`}
        description="Every clean record becomes Ready for Approval. Approval and payment are later, separately-permissioned phases — nothing is paid by this."
        confirmLabel="Complete review"
        isConfirming={complete.isPending}
        onConfirm={() =>
          complete.mutate(runId, {
            onSuccess: () => setCompleting(false),
          })
        }
      />
    </div>
  );
}

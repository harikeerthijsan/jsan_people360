'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { routes } from '@/config/site';
import {
  useApprovalSummary,
  useApprovePayroll,
  useFinalizePayroll,
  useGeneratePayslips,
  useReturnPayroll,
} from '@/features/payroll/hooks';
import { APPROVAL_ACTION_LABELS, RUN_STATUS_LABELS, formatMoney } from '@/features/payroll/types';

/**
 * One run's approval: the summaries an approver reads, the blockers stated
 * verbatim, the full trail of past cycles, and the three decisions —
 * approve, return, finalize. The confirmation dialogs restate the figures
 * being signed off; the server re-validates everything regardless.
 */

export function PayrollRunApprovalPage({ runId }: { runId: string }): React.JSX.Element {
  const summaryQuery = useApprovalSummary(runId);
  const approve = useApprovePayroll();
  const sendBack = useReturnPayroll();
  const finalize = useFinalizePayroll();
  const generatePayslips = useGeneratePayslips();

  const [decision, setDecision] = React.useState<'approve' | 'return' | 'finalize' | null>(null);
  const [comment, setComment] = React.useState('');

  if (summaryQuery.isPending) return <LoadingState />;
  if (summaryQuery.error) return <ErrorState error={summaryQuery.error} />;
  const summary = summaryQuery.data;
  const run = summary.run;

  const closeDecision = (): void => {
    setDecision(null);
    setComment('');
  };

  const figures = (
    <div className="text-sm">
      {(
        [
          ['Payroll period', run.period.name],
          ['Employees', String(run.employee_count)],
          ['Gross', formatMoney(run.total_gross, run.currency)],
          ['Deductions', formatMoney(run.total_deductions, run.currency)],
          ['Net pay', formatMoney(run.total_net, run.currency)],
        ] as const
      ).map(([label, value]) => (
        <div key={label} className="flex justify-between border-b py-1.5">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-medium">{value}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Approval · ${run.period.name}`}
        description={`${run.run_code}. Approval and finalization are recorded decisions: each carries its actor, moment and comment, and nothing here can be edited afterwards.`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={routes.payrollRunDetail(runId)}>Run summary</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={routes.payrollRunReconciliation(runId)}>Reconciliation</Link>
            </Button>
            {run.status === 'pending_approval' ? (
              <>
                <Can permission="payroll:return">
                  <Button variant="outline" onClick={() => setDecision('return')}>
                    Return for correction
                  </Button>
                </Can>
                <Can permission="payroll:approve">
                  <Button disabled={!summary.can_approve} onClick={() => setDecision('approve')}>
                    Approve payroll
                  </Button>
                </Can>
              </>
            ) : null}
            {run.status === 'approved' ? (
              <Can permission="payroll:finalize">
                <Button onClick={() => setDecision('finalize')}>Finalize payroll</Button>
              </Can>
            ) : null}
            {run.status === 'finalized' ? (
              <Can permission="payroll:payslip_generate">
                <Button
                  isLoading={generatePayslips.isPending}
                  onClick={() => generatePayslips.mutate(runId)}
                >
                  Generate payslips
                </Button>
              </Can>
            ) : null}
            {run.status === 'finalized' ? (
              <Can permission="payroll:payslip_view">
                <Button asChild variant="outline">
                  <Link href={routes.payrollPayslips}>Payslips</Link>
                </Button>
              </Can>
            ) : null}
          </div>
        }
      />

      <div className="flex items-center gap-2">
        <Badge variant={run.status === 'returned' ? 'destructive' : 'secondary'}>
          {RUN_STATUS_LABELS[run.status]}
        </Badge>
        {run.approved_by_name ? (
          <span className="text-muted-foreground text-sm">
            Approved by {run.approved_by_name}
            {run.approved_at ? ` · ${new Date(run.approved_at).toLocaleString()}` : ''}
          </span>
        ) : null}
      </div>

      {summary.blockers.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Why this payroll cannot be approved</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <ul className="list-disc space-y-1 pl-5">
              {summary.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total employees" value={run.employee_count} />
        <StatCard label="Gross earnings" value={formatMoney(run.total_gross, run.currency)} />
        <StatCard label="Total deductions" value={formatMoney(run.total_deductions, run.currency)} />
        <StatCard label="Net payroll" value={formatMoney(run.total_net, run.currency)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Employee summary</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {(
              [
                ['Employees included', String(summary.employees.included)],
                ['Employees excluded', String(summary.employees.excluded)],
                ['With adjustments', String(summary.employees.with_adjustments)],
                ['With exceptions', String(summary.employees.with_exceptions)],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between border-b py-2">
                <span className="text-muted-foreground">{label}</span>
                <span>{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Review summary</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {(
              [
                ['Review completed', summary.review.review_completed ? 'Yes' : 'No'],
                ['Reviewer', summary.review.reviewer_name ?? '—'],
                ['Critical exceptions', String(summary.review.critical_exceptions)],
                ['Errors', String(summary.review.error_exceptions)],
                ['Warnings', String(summary.review.warning_exceptions)],
                ['Still open', String(summary.review.open_exceptions)],
                ['Adjustments', String(summary.review.adjustment_count)],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between border-b py-2">
                <span className="text-muted-foreground">{label}</span>
                <span>{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Approval trail</CardTitle>
        </CardHeader>
        <CardContent>
          {summary.trail.length === 0 ? (
            <p className="text-muted-foreground text-sm">Not submitted yet.</p>
          ) : (
            summary.trail.map((step) => (
              <div key={step.id} className="border-b py-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={step.action === 'returned' ? 'destructive' : 'secondary'}>
                    {APPROVAL_ACTION_LABELS[step.action]}
                  </Badge>
                  <span>{step.actor_name ?? 'Unknown'}</span>
                  <span className="text-muted-foreground text-xs">
                    {new Date(step.created_at).toLocaleString()} · net{' '}
                    {formatMoney(step.total_net, run.currency)}
                  </span>
                </div>
                {step.comment ? (
                  <div className="text-muted-foreground mt-1 text-xs">{step.comment}</div>
                ) : null}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* -- Approve ------------------------------------------------------ */}
      <Modal
        open={decision === 'approve'}
        onOpenChange={(open) => {
          if (!open) closeDecision();
        }}
        title="Approve this payroll?"
        description="You are signing off these figures. The comment is required and becomes part of the permanent approval trail."
        confirmLabel="Approve payroll"
        isConfirming={approve.isPending}
        onConfirm={() =>
          approve.mutate({ runId, comment: comment.trim() }, { onSuccess: closeDecision })
        }
      >
        <div className="space-y-3">
          {figures}
          <div className="space-y-1">
            <Label htmlFor="approval-comment">Approval comment (required)</Label>
            <Textarea
              id="approval-comment"
              rows={2}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="e.g. Verified against the reconciliation and June's run."
            />
          </div>
        </div>
      </Modal>

      {/* -- Return ------------------------------------------------------- */}
      <Modal
        open={decision === 'return'}
        onOpenChange={(open) => {
          if (!open) closeDecision();
        }}
        title="Return this payroll for correction?"
        description="The run reopens for review and recalculation. Your reason goes on the run and into the trail — nothing is altered silently."
        confirmLabel="Return for correction"
        confirmVariant="destructive"
        isConfirming={sendBack.isPending}
        onConfirm={() =>
          sendBack.mutate({ runId, reason: comment.trim() }, { onSuccess: closeDecision })
        }
      >
        <div className="space-y-1">
          <Label htmlFor="return-reason">What must be corrected? (required)</Label>
          <Textarea
            id="return-reason"
            rows={2}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        </div>
      </Modal>

      {/* -- Finalize ----------------------------------------------------- */}
      <Modal
        open={decision === 'finalize'}
        onOpenChange={(open) => {
          if (!open) closeDecision();
        }}
        title="Finalize this payroll?"
        description="Finalization writes an immutable snapshot per employee, locks the run against every change, and closes the payroll period. This cannot be undone."
        confirmLabel="Finalize payroll"
        isConfirming={finalize.isPending}
        onConfirm={() =>
          finalize.mutate(
            { runId, comment: comment.trim() || null },
            { onSuccess: closeDecision },
          )
        }
      >
        <div className="space-y-3">
          {figures}
          <div className="space-y-1">
            <Label htmlFor="finalize-comment">Comment (optional)</Label>
            <Textarea
              id="finalize-comment"
              rows={2}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

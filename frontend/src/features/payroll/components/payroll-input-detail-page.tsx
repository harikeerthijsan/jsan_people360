'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { FileSpreadsheet } from 'lucide-react';
import { usePayrollInputDetail, useReviewPayrollInput } from '@/features/payroll/hooks';
import {
  ELIGIBILITY_LABELS,
  EXCEPTION_CATEGORY_LABELS,
  INPUT_STATUS_LABELS,
} from '@/features/payroll/types';

/**
 * One employee's payroll input, in full: the attendance/leave/overtime
 * summary, every exception preparation flagged, and the exact source records
 * the snapshot consumed. Review lives here — a human accepting a flagged
 * input, with a note, without any source record being touched.
 */

export function PayrollInputDetailPage({
  employeeId,
  periodId,
}: {
  employeeId: string;
  periodId: string;
}): React.JSX.Element {
  const query = usePayrollInputDetail(periodId, employeeId);
  const review = useReviewPayrollInput();
  const [reviewing, setReviewing] = React.useState(false);
  const [note, setNote] = React.useState('');

  if (!periodId) {
    return (
      <EmptyState
        icon={FileSpreadsheet}
        title="No period selected"
        description="Open this page from the Payroll Inputs register so it knows which period to show."
      />
    );
  }
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;

  const input = query.data;

  const facts: { label: string; value: React.ReactNode }[] = [
    { label: 'Joining date', value: input.joining_date ?? '—' },
    { label: 'Exit date', value: input.exit_date ?? '—' },
    { label: 'Offboarding', value: input.offboarding_status ?? '—' },
    { label: 'Eligibility', value: ELIGIBILITY_LABELS[input.eligibility] },
    {
      label: 'Proration',
      value: input.proration_required
        ? `Required — ${String(input.eligible_days)} eligible / ${String(input.non_eligible_days)} non-eligible days`
        : 'Not required',
    },
    {
      label: 'Unpaid leave rule',
      value: input.unpaid_leave_deduction
        ? `Deducts (${input.unpaid_leave_basis ?? 'basis unset'})`
        : 'No deduction',
    },
    { label: 'Overtime eligible', value: input.overtime_eligible ? 'Yes' : 'No' },
    { label: 'Prepared', value: new Date(input.prepared_at).toLocaleString() },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${input.employee.full_name} · ${input.period.name}`}
        description="Payroll input data only: day and hour counts read from the source modules. No salary figure exists on this page."
        actions={
          input.status === 'requires_review' ? (
            <Can permission="payroll:inputs_review">
              <Button onClick={() => setReviewing(true)}>Mark reviewed</Button>
            </Can>
          ) : null
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={input.status === 'requires_review' ? 'destructive' : 'secondary'}>
          {INPUT_STATUS_LABELS[input.status]}
        </Badge>
        {input.source_changed ? (
          <Badge variant="outline">Source data changed after snapshot</Badge>
        ) : null}
        {input.exclusion_reason ? (
          <span className="text-muted-foreground text-sm">{input.exclusion_reason}</span>
        ) : null}
        {input.reviewed_at ? (
          <span className="text-muted-foreground text-sm">
            Reviewed by {input.reviewed_by_name ?? 'unknown'}
            {input.review_note ? ` — ${input.review_note}` : ''}
          </span>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Working days" value={input.working_days} />
        <StatCard label="Present" value={input.present_days} />
        <StatCard label="Half days" value={input.half_days} />
        <StatCard label="Absent" value={input.absent_days} />
        <StatCard label="Weekly offs" value={input.weekly_off_days} />
        <StatCard label="Holidays" value={input.holiday_days} />
        <StatCard label="Paid leave" value={input.paid_leave_days} />
        <StatCard label="Unpaid leave" value={input.unpaid_leave_days} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Overtime</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between border-b py-2">
              <span>Approved hours</span>
              <b>{input.approved_overtime_hours}</b>
            </div>
            <div className="flex justify-between border-b py-2">
              <span>Pending hours</span>
              <b>{input.pending_overtime_hours}</b>
            </div>
            <div className="flex justify-between py-2">
              <span>Total recorded</span>
              <b>{input.overtime_hours}</b>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Employee</CardTitle>
          </CardHeader>
          <CardContent>
            {facts.map((fact) => (
              <div key={fact.label} className="flex justify-between border-b py-2 text-sm">
                <span className="text-muted-foreground">{fact.label}</span>
                <span>{fact.value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Exceptions</CardTitle>
        </CardHeader>
        <CardContent>
          {input.exceptions.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              Nothing needs a human: preparation found no payroll-impacting issue.
            </p>
          ) : (
            input.exceptions.map((exception) => (
              <div key={exception.id} className="flex items-start gap-3 border-b py-2 text-sm">
                <Badge variant="outline">{EXCEPTION_CATEGORY_LABELS[exception.category]}</Badge>
                <div>
                  <div>{exception.message}</div>
                  <div className="text-muted-foreground font-mono text-xs">
                    {exception.code}
                    {exception.occurred_on ? ` · ${exception.occurred_on}` : ''}
                  </div>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Snapshot sources</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-2 text-sm">
            The exact records this input was built from, at the version seen during preparation.
            The records stay owned by their own modules.
          </p>
          {input.sources.length === 0 ? (
            <p className="text-muted-foreground text-sm">No source records in this period.</p>
          ) : (
            <div className="grid gap-1 sm:grid-cols-2">
              {input.sources.map((source) => (
                <div
                  key={`${source.source_type}-${source.source_id}`}
                  className="text-muted-foreground font-mono text-xs"
                >
                  {source.source_type} · {source.source_id.slice(0, 8)} ·{' '}
                  {new Date(source.source_updated_at).toLocaleString()}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={reviewing}
        onOpenChange={setReviewing}
        title={`Mark ${input.employee.full_name}'s input reviewed?`}
        description="The input returns to Ready. The flagged issues stay recorded, and no attendance or leave record changes."
        confirmLabel="Mark reviewed"
        isConfirming={review.isPending}
        onConfirm={() =>
          review.mutate(
            { inputId: input.id, note: note.trim() || null },
            { onSuccess: () => setReviewing(false) },
          )
        }
      />
      {/* The note travels with the confirmation; shown here so it can be
          written before the dialog confirms. */}
      {input.status === 'requires_review' ? (
        <Can permission="payroll:inputs_review">
          <div className="max-w-xl space-y-1">
            <label className="text-sm font-medium" htmlFor="review-note">
              Review note (recorded in the audit trail)
            </label>
            <Textarea
              id="review-note"
              rows={2}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What was checked, and why the input is acceptable"
            />
          </div>
        </Can>
      ) : null}
    </div>
  );
}

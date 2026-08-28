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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { routes } from '@/config/site';
import {
  useAddSettlementAdjustment,
  useApproveSettlement,
  useCalculateSettlement,
  useCompleteSettlementReview,
  useDecideSettlementAdjustment,
  useFinalizeSettlement,
  useReopenSettlement,
  useSettlement,
  useSubmitSettlement,
} from '@/features/payroll/hooks';
import {
  SETTLEMENT_ADJUSTMENT_TYPE_LABELS,
  SETTLEMENT_ITEM_CATEGORY_LABELS,
  SETTLEMENT_STATUS_LABELS,
  formatMoney,
  type SettlementAdjustmentType,
  type SettlementItemCategory,
} from '@/features/payroll/types';

/**
 * The settlement review screen, top to bottom in the order a reviewer reads
 * it: who and when, the final salary, leave, attendance and overtime,
 * assets, then the four components and their sum. Every act — recalculate,
 * propose, decide, submit, review, approve, reopen, settle — is its own
 * permission on the server; the buttons here only reflect them.
 */

const CATEGORIES: SettlementItemCategory[] = ['earning', 'encashment', 'adjustment', 'deduction'];

function Rows({ pairs }: { pairs: ReadonlyArray<readonly [string, React.ReactNode]> }): React.JSX.Element {
  return (
    <div className="text-sm">
      {pairs.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-4 border-b py-2">
          <span className="text-muted-foreground">{label}</span>
          <span className="text-right">{value}</span>
        </div>
      ))}
    </div>
  );
}

export function PayrollSettlementDetailPage({ settlementId }: { settlementId: string }): React.JSX.Element {
  const query = useSettlement(settlementId);
  const calculate = useCalculateSettlement();
  const addAdjustment = useAddSettlementAdjustment();
  const decide = useDecideSettlementAdjustment();
  const submit = useSubmitSettlement();
  const completeReview = useCompleteSettlementReview();
  const approve = useApproveSettlement();
  const reopen = useReopenSettlement();
  const finalize = useFinalizeSettlement();

  const [dialog, setDialog] = React.useState<'adjust' | 'approve' | 'reopen' | 'finalize' | null>(null);
  const [text, setText] = React.useState('');
  const [form, setForm] = React.useState({ adjustment_type: 'final_bonus' as SettlementAdjustmentType, name: '', amount: '', reason: '' });
  const close = (): void => {
    setDialog(null);
    setText('');
    setForm({ adjustment_type: 'final_bonus', name: '', amount: '', reason: '' });
  };

  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  const s = query.data;
  const money = (value: string | null): string => (value === null ? '—' : formatMoney(value, s.currency));
  const editable = s.status === 'draft' || s.status === 'under_review';

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${s.employee.full_name} · Final settlement`}
        description={`${s.settlement_code}. Computed only from existing records; anything needing a company decision is an adjustment with a reason, counted once approved.`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link href={routes.payrollSettlements}>All exits</Link>
            </Button>
            {editable ? (
              <Can permission="payroll:settlement_update">
                <Button variant="outline" isLoading={calculate.isPending} onClick={() => calculate.mutate(settlementId)}>
                  Recalculate
                </Button>
                <Button variant="outline" onClick={() => setDialog('adjust')}>
                  Propose adjustment
                </Button>
              </Can>
            ) : null}
            {s.status === 'draft' ? (
              <Can permission="payroll:settlement_update">
                <Button isLoading={submit.isPending} onClick={() => submit.mutate(settlementId)}>
                  Submit for review
                </Button>
              </Can>
            ) : null}
            {s.status === 'under_review' && !s.review_completed_at ? (
              <Can permission="payroll:settlement_update">
                <Button isLoading={completeReview.isPending} onClick={() => completeReview.mutate(settlementId)}>
                  Complete review
                </Button>
              </Can>
            ) : null}
            {s.status === 'under_review' ? (
              <Can permission="payroll:settlement_approve">
                <Button disabled={!s.can_approve} onClick={() => setDialog('approve')}>
                  Approve
                </Button>
              </Can>
            ) : null}
            {s.status === 'approved' ? (
              <>
                <Can permission="payroll:settlement_approve">
                  <Button variant="outline" onClick={() => setDialog('reopen')}>
                    Reopen
                  </Button>
                </Can>
                <Can permission="payroll:settlement_finalize">
                  <Button onClick={() => setDialog('finalize')}>Settle</Button>
                </Can>
              </>
            ) : null}
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={s.status === 'settled' ? 'secondary' : 'outline'}>{SETTLEMENT_STATUS_LABELS[s.status]}</Badge>
        {s.status === 'settled' ? (
          <span className="text-muted-foreground text-sm">
            Settled by {s.settled_by_name ?? 'unknown'}
            {s.settlement_reference ? ` · ref ${s.settlement_reference}` : ''} — read-only.
          </span>
        ) : null}
        {s.approved_by_name ? (
          <span className="text-muted-foreground text-sm">Approved by {s.approved_by_name}: {s.approval_comment}</span>
        ) : null}
      </div>

      {s.issues.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Review notes{s.critical_issue_count > 0 ? ` · ${String(s.critical_issue_count)} blocking` : ''}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {s.issues.map((issue) => (
                <li key={issue.message} className="flex gap-2">
                  <Badge variant={issue.severity === 'critical' ? 'destructive' : 'outline'}>{issue.severity}</Badge>
                  <span>{issue.message}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Final earnings" value={money(s.final_earnings)} />
        <StatCard label="Approved encashments" value={money(s.approved_encashments)} />
        <StatCard label="Approved adjustments" value={money(s.approved_adjustments)} />
        <StatCard label="Final deductions" value={money(s.final_deductions)} />
        <StatCard label="Settlement amount" value={money(s.settlement_amount)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Employee & employment</CardTitle></CardHeader>
          <CardContent>
            <Rows
              pairs={[
                ['Employee', `${s.employee.full_name} · ${s.employee.employee_code}`],
                ['Department', s.department ?? '—'],
                ['Joining date', s.joining_date ?? '—'],
                ['Last working date', s.last_working_date],
                ['Exit', `${s.exit_type}${s.exit_reason ? ` — ${s.exit_reason}` : ''}`],
                ['Offboarding', s.offboarding_status.replace('_', ' ')],
                ['Final payroll period', s.final_period_name ?? '—'],
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Final salary</CardTitle></CardHeader>
          <CardContent>
            <Rows
              pairs={[
                ['Monthly gross', money(s.monthly_gross)],
                ['Basic salary', money(s.basic_salary)],
                ['Daily rate', s.daily_rate ?? '—'],
                ['Paid through payroll until', s.paid_through ?? 'never'],
                ['Unpaid salary days', String(s.unpaid_salary_days)],
                ['Unpaid leave days (final window)', s.unpaid_leave_days],
                ['Overtime hours (final window)', s.overtime_hours],
              ]}
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Leave balance</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {s.leave_summary.length === 0 ? <p className="text-muted-foreground">No leave balances for the exit year.</p> : null}
            {s.leave_summary.map((row) => (
              <div key={row.code} className="flex justify-between gap-2 border-b py-2">
                <span>{row.leave_type}{row.is_paid ? '' : ' (unpaid)'}</span>
                <span className="text-muted-foreground">eligible {row.eligible} · used {row.used} · remaining <b>{row.remaining}</b>{row.encashable ? ' · encashable' : ''}</span>
              </div>
            ))}
            <p className="text-muted-foreground mt-2 text-xs">No leave-encashment policy is configured; encashment is recorded only as an approved adjustment.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Assets</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {s.assets.length === 0 ? <p className="text-muted-foreground">No assets on loan.</p> : null}
            {s.assets.map((row) => (
              <div key={`${row.asset_name}-${row.asset_tag ?? ''}`} className="flex justify-between gap-2 border-b py-2">
                <span>{row.asset_name}{row.asset_tag ? ` · ${row.asset_tag}` : ''}</span>
                <span className="text-right">
                  <Badge variant={['returned', 'waived'].includes(row.return_status) ? 'secondary' : 'destructive'}>{row.return_status}</Badge>
                  {row.recovery_approved && row.recovery_amount ? <div className="text-xs">recovery {money(row.recovery_amount)} (approved)</div> : row.return_status === 'returned' ? <div className="text-muted-foreground text-xs">no recovery</div> : null}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Settlement components</CardTitle></CardHeader>
        <CardContent className="text-sm">
          {CATEGORIES.map((category) => {
            const items = s.items.filter((item) => item.category === category);
            return (
              <div key={category} className="mb-4">
                <div className="text-muted-foreground mb-1 text-xs uppercase tracking-wide">{SETTLEMENT_ITEM_CATEGORY_LABELS[category]}</div>
                {items.length === 0 ? <div className="text-muted-foreground">None.</div> : null}
                {items.map((item) => (
                  <div key={item.id} className="flex items-start justify-between gap-4 border-b py-2">
                    <div>
                      <div className="font-medium">{item.name}{item.source === 'adjustment' ? ' (approved adjustment)' : ''}</div>
                      {item.basis ? <div className="text-muted-foreground text-xs">{item.basis}</div> : null}
                    </div>
                    <div className="whitespace-nowrap">{money(item.amount)}</div>
                  </div>
                ))}
              </div>
            );
          })}
          <div className="flex justify-between border-t pt-3 text-base font-semibold">
            <span>Final settlement amount</span>
            <span>{money(s.settlement_amount)}</span>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">= final earnings + approved encashments + approved adjustments − final deductions</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Adjustments</CardTitle></CardHeader>
        <CardContent className="text-sm">
          {s.adjustments.length === 0 ? <p className="text-muted-foreground">None proposed.</p> : null}
          {s.adjustments.map((a) => (
            <div key={a.id} className="flex items-start justify-between gap-4 border-b py-2">
              <div>
                <div className="font-medium">
                  {a.name} <Badge variant={a.status === 'approved' ? 'secondary' : a.status === 'rejected' ? 'destructive' : 'outline'}>{a.status}</Badge>
                </div>
                <div className="text-muted-foreground text-xs">
                  {SETTLEMENT_ADJUSTMENT_TYPE_LABELS[a.adjustment_type]} · {a.is_earning ? 'adds' : 'deducts'} · {a.reason}
                  {a.decided_by_name ? ` · decided by ${a.decided_by_name}${a.decision_note ? `: ${a.decision_note}` : ''}` : ''}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="whitespace-nowrap">{money(a.amount)}</span>
                {a.status === 'pending' && editable ? (
                  <Can permission="payroll:settlement_approve">
                    <Button size="sm" variant="outline" isLoading={decide.isPending} onClick={() => decide.mutate({ settlementId, adjustmentId: a.id, approve: true })}>Approve</Button>
                    <Button size="sm" variant="ghost" isLoading={decide.isPending} onClick={() => decide.mutate({ settlementId, adjustmentId: a.id, approve: false })}>Reject</Button>
                  </Can>
                ) : null}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Modal
        open={dialog === 'adjust'}
        onOpenChange={(open) => { if (!open) close(); }}
        title="Propose an adjustment"
        description="Counted only once an approver approves it. The type fixes whether it adds or deducts."
        confirmLabel="Propose"
        isConfirming={addAdjustment.isPending}
        onConfirm={() =>
          addAdjustment.mutate(
            { settlementId, payload: { adjustment_type: form.adjustment_type, name: form.name.trim(), amount: form.amount.trim(), reason: form.reason.trim() } },
            { onSuccess: close },
          )
        }
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="adj-type">Type</Label>
            <select id="adj-type" className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm" value={form.adjustment_type} onChange={(e) => setForm((f) => ({ ...f, adjustment_type: e.target.value as SettlementAdjustmentType }))}>
              {(Object.keys(SETTLEMENT_ADJUSTMENT_TYPE_LABELS) as SettlementAdjustmentType[]).map((t) => (
                <option key={t} value={t}>{SETTLEMENT_ADJUSTMENT_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1"><Label htmlFor="adj-name">Name</Label><Input id="adj-name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></div>
          <div className="space-y-1"><Label htmlFor="adj-amount">Amount</Label><Input id="adj-amount" inputMode="decimal" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} /></div>
          <div className="space-y-1"><Label htmlFor="adj-reason">Reason (required)</Label><Textarea id="adj-reason" rows={2} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} /></div>
        </div>
      </Modal>

      <Modal
        open={dialog === 'approve'}
        onOpenChange={(open) => { if (!open) close(); }}
        title="Approve this settlement?"
        description={`Settlement amount ${money(s.settlement_amount)}. The gates are re-checked at the moment of approval.`}
        confirmLabel="Approve"
        isConfirming={approve.isPending}
        onConfirm={() => approve.mutate({ settlementId, comment: text.trim() }, { onSuccess: close })}
      >
        <div className="space-y-1"><Label htmlFor="approve-comment">Approval comment (required)</Label><Textarea id="approve-comment" rows={2} value={text} onChange={(e) => setText(e.target.value)} /></div>
      </Modal>

      <Modal
        open={dialog === 'reopen'}
        onOpenChange={(open) => { if (!open) close(); }}
        title="Reopen this settlement?"
        description="It returns to draft; approval and review are cleared and must be redone."
        confirmLabel="Reopen"
        confirmVariant="destructive"
        isConfirming={reopen.isPending}
        onConfirm={() => reopen.mutate({ settlementId, reason: text.trim() }, { onSuccess: close })}
      >
        <div className="space-y-1"><Label htmlFor="reopen-reason">Reason (required)</Label><Textarea id="reopen-reason" rows={2} value={text} onChange={(e) => setText(e.target.value)} /></div>
      </Modal>

      <Modal
        open={dialog === 'finalize'}
        onOpenChange={(open) => { if (!open) close(); }}
        title="Settle this settlement?"
        description={`${money(s.settlement_amount)} becomes the final, read-only settlement and is released to the employee. This cannot be undone.`}
        confirmLabel="Settle"
        isConfirming={finalize.isPending}
        onConfirm={() => finalize.mutate({ settlementId, reference: text.trim() || null }, { onSuccess: close })}
      >
        <div className="space-y-1"><Label htmlFor="settle-ref">Settlement reference (optional)</Label><Input id="settle-ref" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. payment reference" /></div>
      </Modal>
    </div>
  );
}

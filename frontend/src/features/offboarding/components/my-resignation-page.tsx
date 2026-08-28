'use client';

import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useMyResignation, useSubmitResignation, useWithdrawResignation } from '@/features/offboarding/hooks';
import { RESIGNATION_STATUS_LABELS, type MyResignation } from '@/features/offboarding/types';

/**
 * My Resignation.
 *
 * The form posts four fields and no identity. Which employee this is comes from
 * the session on the server, so there is nothing here to point at somebody
 * else -- the same property the rest of the employee portal has.
 *
 * When a resignation exists, the form is replaced by its status rather than
 * sitting underneath it. Somebody who has already resigned does not need a
 * second form; they need to know where the first one has got to.
 */

const DEFAULT_REASON = 'Career change';

const REASONS = [
  DEFAULT_REASON,
  'Better opportunity',
  'Higher studies',
  'Relocation',
  'Personal reasons',
  'Health reasons',
  'Retirement',
  'Other',
];

function statusTone(status: MyResignation['status']): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'rejected' || status === 'cancelled') return 'destructive';
  if (status === 'completed') return 'secondary';
  if (status === 'withdrawn') return 'outline';
  return 'default';
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function MyResignationPage(): React.JSX.Element {
  const query = useMyResignation();
  const submit = useSubmitResignation();
  const withdraw = useWithdrawResignation();

  const [resignationDate, setResignationDate] = React.useState(today());
  const [lastDay, setLastDay] = React.useState('');
  const [reason, setReason] = React.useState(DEFAULT_REASON);
  const [comments, setComments] = React.useState('');

  const resignation = query.data ?? null;

  const onSubmit = (event: React.FormEvent): void => {
    event.preventDefault();
    submit.mutate({
      resignation_date: resignationDate,
      proposed_last_working_day: lastDay,
      reason,
      comments: comments || null,
    });
  };

  if (query.isLoading) {
    return <EmptyState title="Loading" description="Fetching your resignation status." />;
  }

  if (!resignation) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Resignation"
          description="Submit your resignation. Your manager reviews it first, then HR."
        />
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Submit a resignation</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="resignation-date">Resignation date</Label>
                  <Input
                    id="resignation-date"
                    type="date"
                    value={resignationDate}
                    onChange={(event) => setResignationDate(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last-day">Proposed last working day</Label>
                  <Input
                    id="last-day"
                    type="date"
                    min={resignationDate}
                    value={lastDay}
                    onChange={(event) => setLastDay(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="reason">Reason</Label>
                <select
                  id="reason"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                >
                  {REASONS.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="comments">Comments (optional)</Label>
                <Textarea
                  id="comments"
                  rows={4}
                  value={comments}
                  onChange={(event) => setComments(event.target.value)}
                  placeholder="Anything you would like your manager and HR to know."
                />
              </div>

              <p className="text-muted-foreground text-sm">
                Your notice period is taken from your employment type. HR confirms the final last working day
                when they process this.
              </p>

              <Button type="submit" disabled={submit.isPending || !lastDay}>
                {submit.isPending ? 'Submitting…' : 'Submit resignation'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  const notice = resignation.notice;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Resignation"
        description={`${resignation.resignation_code} — submitted ${resignation.resignation_date}`}
        actions={
          resignation.can_withdraw ? (
            <Button
              variant="outline"
              onClick={() => withdraw.mutate(undefined)}
              disabled={withdraw.isPending}
            >
              Withdraw resignation
            </Button>
          ) : null
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Status" value={RESIGNATION_STATUS_LABELS[resignation.status]} />
        <StatCard label="Notice period" value={`${String(notice?.notice_period_days ?? 0)} days`} />
        <StatCard
          label="Approved last working day"
          value={resignation.approved_last_working_day ?? 'Awaiting HR'}
        />
        <StatCard label="Days remaining" value={notice ? notice.remaining_days : '—'} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row label="Reason" value={resignation.reason} />
            <Row label="Proposed last working day" value={resignation.proposed_last_working_day} />
            <Row label="Notice status" value={notice?.notice_status ?? '—'} />
            {resignation.comments ? <Row label="Your comments" value={resignation.comments} /> : null}
            {resignation.manager_comments ? (
              <Row label="Manager's comments" value={resignation.manager_comments} />
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {resignation.history.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-4 text-sm">
                  <div>
                    <p className="font-medium capitalize">{entry.action.replace(/_/g, ' ')}</p>
                    {entry.comments ? <p className="text-muted-foreground">{entry.comments}</p> : null}
                  </div>
                  <Badge variant={statusTone(resignation.status)} className="shrink-0">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </Badge>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

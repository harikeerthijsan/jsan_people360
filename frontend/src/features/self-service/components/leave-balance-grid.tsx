'use client';

import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { MyLeaveBalance } from '@/features/self-service/types';
import { cn } from '@/lib/utils';

/**
 * The five figures an employee actually asks about, per leave type.
 *
 * Allocated, accrued, used, pending and available are shown together rather
 * than reduced to "days left", because they answer different questions and the
 * one people dispute is the difference between *pending* and *used*. Held days
 * come back if a request is turned down; spent days do not. A single combined
 * figure is the kind of number that produces a support ticket.
 *
 * None of these are computed here. They come from the leave engine, which is
 * the only thing that knows what a working day is.
 */

interface FigureProps {
  label: string;
  value: string;
  hint?: string;
  emphasis?: boolean;
}

function Figure({ label, value, hint, emphasis = false }: FigureProps): React.JSX.Element {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd
        className={cn('tabular-nums', emphasis ? 'text-lg font-semibold' : 'text-sm font-medium')}
        title={hint}
      >
        {value}
      </dd>
    </div>
  );
}

export function LeaveBalanceCard({ balance }: { balance: MyLeaveBalance }): React.JSX.Element {
  const accrued = Number(balance.accrued);
  const consumed = Number(balance.used) + Number(balance.pending);
  const filled = accrued > 0 ? Math.min((consumed / accrued) * 100, 100) : 0;
  const exhausted = Number(balance.available) <= 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <CardTitle className="text-sm font-medium">{balance.leave_type?.name ?? 'Leave'}</CardTitle>
        {balance.is_paid ? null : <Badge variant="outline">Unpaid</Badge>}
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="text-2xl font-semibold tabular-nums">
          {balance.available}
          <span className="text-muted-foreground ml-1 text-sm font-normal">available</span>
        </p>

        <div
          aria-label={`${balance.available} of ${balance.accrued} days available`}
          className="bg-muted h-2 rounded-full"
          role="img"
        >
          <div
            className={cn('h-full rounded-full', exhausted ? 'bg-destructive' : 'bg-primary')}
            style={{ width: `${String(filled)}%` }}
          />
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Figure label="Allocated" value={balance.allocated} />
          <Figure hint="Allocated plus anything carried forward" label="Accrued" value={balance.accrued} />
          <Figure label="Used" value={balance.used} />
          <Figure hint="Held by a request awaiting a decision" label="Pending" value={balance.pending} />
        </dl>

        {balance.requires_document ? (
          <p className="text-muted-foreground text-xs">A supporting document is required.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function LeaveBalanceGrid({ balances }: { balances: MyLeaveBalance[] }): React.JSX.Element {
  if (balances.length === 0) {
    return <p className="text-muted-foreground text-sm">No leave types are configured yet.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {balances.map((balance) => (
        <LeaveBalanceCard balance={balance} key={balance.leave_type_id} />
      ))}
    </div>
  );
}

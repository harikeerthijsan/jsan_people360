'use client';

import { FileText } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AppError } from '@/lib/errors';
import { useMySettlement } from '@/features/payroll/hooks';
import { SETTLEMENT_ITEM_CATEGORY_LABELS, formatMoney, type SettlementItemCategory } from '@/features/payroll/types';

/**
 * The employee's own final settlement — visible only once the organization
 * has settled and released it, and showing the figures and their breakdown
 * alone: no internal comments, approvals or review notes.
 */

const CATEGORIES: SettlementItemCategory[] = ['earning', 'encashment', 'adjustment', 'deduction'];

export function MySettlementPage(): React.JSX.Element {
  const query = useMySettlement();
  if (query.isPending) return <LoadingState />;
  if (query.error) {
    if (query.error instanceof AppError && query.error.status === 404) {
      return (
        <div className="space-y-6">
          <PageHeader title="My Final Settlement" />
          <EmptyState
            icon={FileText}
            title="No settlement released yet"
            description="Your final settlement appears here once the organization has settled and released it."
          />
        </div>
      );
    }
    return <ErrorState error={query.error} />;
  }
  const s = query.data;
  const money = (value: string): string => formatMoney(value, s.currency);
  return (
    <div className="space-y-6">
      <PageHeader
        title="My Final Settlement"
        description={`${s.settlement_code} · last working date ${s.last_working_date}${s.settled_at ? ` · settled ${new Date(s.settled_at).toLocaleDateString()}` : ''}`}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Final earnings" value={money(s.final_earnings)} />
        <StatCard label="Encashments" value={money(s.approved_encashments)} />
        <StatCard label="Adjustments" value={money(s.approved_adjustments)} />
        <StatCard label="Deductions" value={money(s.final_deductions)} />
        <StatCard label="Settlement amount" value={money(s.settlement_amount)} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {CATEGORIES.map((category) => {
            const items = s.items.filter((item) => item.category === category);
            if (items.length === 0) return null;
            return (
              <div key={category} className="mb-4">
                <div className="text-muted-foreground mb-1 text-xs uppercase tracking-wide">{SETTLEMENT_ITEM_CATEGORY_LABELS[category]}</div>
                {items.map((item) => (
                  <div key={item.id} className="flex items-start justify-between gap-4 border-b py-2">
                    <div>
                      <div className="font-medium">{item.name}</div>
                      {item.basis ? <div className="text-muted-foreground text-xs">{item.basis}</div> : null}
                    </div>
                    <div className="whitespace-nowrap">{money(item.amount)}</div>
                  </div>
                ))}
              </div>
            );
          })}
          <div className="flex justify-between border-t pt-3 text-base font-semibold">
            <span>Settlement amount</span>
            <span>{money(s.settlement_amount)}</span>
          </div>
          {s.settlement_reference ? <p className="text-muted-foreground mt-2 text-xs">Reference: {s.settlement_reference}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}

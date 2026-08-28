'use client';

import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAssetDashboard } from '@/features/assets/hooks';
import type { CountByLabel } from '@/features/assets/types';

/**
 * Asset dashboard.
 *
 * Every figure comes from the API, which counts rows. Nothing here is derived
 * from a page of results or hardcoded -- §19 asks for real data, and a
 * dashboard built from whatever the list endpoint happened to return would be
 * wrong the moment the inventory outgrew one page.
 */

function Breakdown({ title, rows }: { title: string; rows: CountByLabel[] }): React.JSX.Element {
  const highest = Math.max(1, ...rows.map((row) => row.count));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing to show yet.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li key={row.label} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="capitalize">{row.label.replace(/_/g, ' ')}</span>
                  <span className="font-medium tabular-nums">{row.count}</span>
                </div>
                <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{ width: `${String(Math.round((row.count / highest) * 100))}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function AssetDashboardPage(): React.JSX.Element {
  const query = useAssetDashboard();

  if (query.isLoading) {
    return <EmptyState title="Loading" description="Counting the register." />;
  }
  const data = query.data;
  if (!data) {
    return <EmptyState title="Unavailable" description="The dashboard could not be loaded." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Asset dashboard" description="The register at a glance, counted live." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total assets" value={data.total} />
        <StatCard label="Available" value={data.available} />
        <StatCard label="Assigned" value={data.assigned} />
        <StatCard label="Under maintenance" value={data.under_maintenance} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Reserved" value={data.reserved} />
        <StatCard label="Damaged" value={data.damaged} />
        <StatCard label="Lost" value={data.lost} />
        <StatCard label="Retired" value={data.retired} />
        <StatCard label="Disposed" value={data.disposed} />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Warranty expiring soon"
          value={data.warranty_expiring_soon}
          hint="Within the next 30 days"
        />
        <StatCard label="Warranty expired" value={data.warranty_expired} />
        <StatCard label="Maintenance due" value={data.maintenance_due} hint="Scheduled and past due" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Breakdown title="By category" rows={data.by_category} />
        <Breakdown title="By location" rows={data.by_location} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <RecentCard title="Recent assignments" rows={data.recent_assignments} />
        <RecentCard title="Recent returns" rows={data.recent_returns} />
        <RecentCard title="Recent transfers" rows={data.recent_transfers} />
      </div>
    </div>
  );
}

function RecentCard({
  title,
  rows,
}: {
  title: string;
  rows: { id: string; notes: string | null; new_value: string | null; created_at: string }[];
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing recently.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li key={row.id} className="flex items-start justify-between gap-3 text-sm">
                <span>{row.notes ?? row.new_value ?? '—'}</span>
                <Badge variant="outline" className="shrink-0">
                  {new Date(row.created_at).toLocaleDateString()}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

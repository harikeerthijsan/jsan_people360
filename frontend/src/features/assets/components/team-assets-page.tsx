'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { useTeamAssets } from '@/features/assets/hooks';
import { ASSET_CONDITION_LABELS, ASSET_STATUS_LABELS, type TeamAssetRow } from '@/features/assets/types';

/**
 * Team assets.
 *
 * Direct reports only, resolved by the server from the reporting line -- the
 * endpoint takes no manager id, so this cannot be pointed at another team.
 *
 * Read only for the same reason as the employee page: managers hold
 * `assets:view` and none of the custody permissions, so there is no route
 * behind a button here even if one were drawn.
 *
 * The filter is client-side, deliberately. A team is a handful of people
 * holding a handful of things, all of it already in one response; a server
 * round trip per keystroke would be slower and no more correct. The *register*
 * screen filters server-side, because that one is unbounded.
 */

export function TeamAssetsPage(): React.JSX.Element {
  const query = useTeamAssets();
  const [filter, setFilter] = React.useState('');

  const rows = query.data ?? [];
  const term = filter.trim().toLowerCase();
  const visible = term
    ? rows.filter((row) =>
        [row.employee.full_name, row.name, row.asset_tag, row.category]
          .join(' ')
          .toLowerCase()
          .includes(term),
      )
    : rows;

  const overdue = rows.filter(
    (row) => row.expected_return_date !== null && new Date(row.expected_return_date) < new Date(),
  ).length;

  const columns: DataTableColumn<TeamAssetRow>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => row.employee.full_name },
    {
      id: 'asset',
      header: 'Asset',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">{row.category}</p>
        </div>
      ),
    },
    { id: 'tag', header: 'Tag', cell: (row) => <span className="tabular-nums">{row.asset_tag}</span> },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="secondary">{ASSET_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'condition',
      header: 'Condition',
      cell: (row) => <Badge variant="outline">{ASSET_CONDITION_LABELS[row.condition]}</Badge>,
    },
    { id: 'assigned', header: 'Assigned', cell: (row) => row.assigned_date },
    {
      id: 'due',
      header: 'Expected back',
      cell: (row) =>
        row.expected_return_date ? (
          <span
            className={new Date(row.expected_return_date) < new Date() ? 'text-destructive font-medium' : ''}
          >
            {row.expected_return_date}
          </span>
        ) : (
          '—'
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team assets"
        description="What the people who report to you are holding. Contact IT to change any of it."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Assets issued" value={rows.length} />
        <StatCard label="People holding assets" value={new Set(rows.map((r) => r.employee.id)).size} />
        <StatCard label="Past expected return" value={overdue} />
      </div>

      <Input
        placeholder="Filter by employee, asset or tag"
        className="max-w-sm"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />

      <DataTable
        rows={visible}
        columns={columns}
        getRowId={(row) => row.assignment_id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No assets issued"
        emptyDescription="Nobody who reports to you currently holds company property."
      />
    </div>
  );
}

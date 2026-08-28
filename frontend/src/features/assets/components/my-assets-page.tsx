'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { useMyAssets } from '@/features/assets/hooks';
import { ASSET_CONDITION_LABELS, ASSET_STATUS_LABELS, type MyAsset } from '@/features/assets/types';

/**
 * My Assets.
 *
 * Read only, and that is the server's doing rather than this component's: there
 * is no employee-facing endpoint that assigns, edits, transfers or returns
 * anything. The screen has no buttons because the API has no routes, which is
 * the right order for those two facts.
 *
 * The response carries no purchase cost or vendor -- the read model omits them
 * -- so there is nothing here to remember not to render.
 */

function overdue(expected: string | null): boolean {
  return expected !== null && new Date(expected) < new Date();
}

export function MyAssetsPage(): React.JSX.Element {
  const query = useMyAssets();
  const rows = query.data ?? [];

  const columns: DataTableColumn<MyAsset>[] = [
    {
      id: 'name',
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
      id: 'make',
      header: 'Make',
      cell: (row) => [row.brand, row.model].filter(Boolean).join(' ') || '—',
    },
    { id: 'serial', header: 'Serial', cell: (row) => row.serial_number ?? '—' },
    { id: 'assigned', header: 'Assigned', cell: (row) => row.assigned_date },
    {
      id: 'condition',
      header: 'Condition',
      cell: (row) => <Badge variant="outline">{ASSET_CONDITION_LABELS[row.condition_at_assignment]}</Badge>,
    },
    {
      id: 'due',
      header: 'Expected back',
      cell: (row) =>
        row.expected_return_date ? (
          <span className={overdue(row.expected_return_date) ? 'text-destructive font-medium' : ''}>
            {row.expected_return_date}
          </span>
        ) : (
          '—'
        ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="secondary">{ASSET_STATUS_LABELS[row.status]}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My assets"
        description="Company property currently issued to you. Contact IT to return or report anything."
      />
      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No assets issued"
        emptyDescription="Nothing is currently assigned to you."
      />
    </div>
  );
}

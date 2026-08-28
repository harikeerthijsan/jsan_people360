'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { CardDescription } from '@/components/ui/card';
import { TeamMemberCell } from '@/features/manager/components/widgets';
import { useTeamDocumentStatus } from '@/features/manager/hooks';
import type { TeamDocumentStatus } from '@/features/manager/types';

/**
 * Team document completion.
 *
 * Counts, and nothing else. There is no document name, no classification and no
 * file on this screen because there is none in the response: an Aadhaar scan
 * and a signed policy are indistinguishable here, which is what makes the
 * question "is this person's paperwork complete" answerable without handing a
 * manager the paperwork.
 *
 * Opening a document is the vault's job, scoped and audited separately. A
 * manager who is entitled to one reaches it there.
 */
export function TeamDocumentsPage(): React.JSX.Element {
  const status = useTeamDocumentStatus();
  const rows = status.data ?? [];

  const totals = rows.reduce(
    (running, row) => ({
      total: running.total + row.total,
      approved: running.approved + row.approved,
      pending: running.pending + row.pending,
      rejected: running.rejected + row.rejected,
    }),
    { total: 0, approved: 0, pending: 0, rejected: 0 },
  );

  const columns: DataTableColumn<TeamDocumentStatus>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    {
      id: 'total',
      header: 'Filed',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.total}</span>,
    },
    {
      id: 'approved',
      header: 'Approved',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.approved}</span>,
    },
    {
      id: 'pending',
      header: 'Awaiting review',
      align: 'right',
      cell: (row) =>
        row.pending > 0 ? (
          <Badge variant="warning">{row.pending}</Badge>
        ) : (
          <span className="text-muted-foreground tabular-nums">0</span>
        ),
    },
    {
      id: 'rejected',
      header: 'Rejected',
      align: 'right',
      cell: (row) =>
        row.rejected > 0 ? (
          <Badge variant="destructive">{row.rejected}</Badge>
        ) : (
          <span className="text-muted-foreground tabular-nums">0</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Team Documents" description="How complete your direct reports' paperwork is." />

      <CardDescription>
        Counts only. This screen never shows a document, its classification or its contents — reaching one
        needs the document vault, which is scoped and audited separately.
      </CardDescription>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard hint="across the team" label="Filed" value={totals.total} />
        <StatCard hint="reviewed and accepted" label="Approved" value={totals.approved} />
        <StatCard hint="with HR" label="Awaiting review" value={totals.pending} />
        <StatCard hint="need re-uploading" label="Rejected" value={totals.rejected} />
      </div>

      <DataTable
        caption="Team document completion"
        columns={columns}
        emptyDescription="Nobody reports to you yet."
        emptyTitle="No team members"
        error={status.error}
        getRowId={(row) => row.employee.id}
        isLoading={status.isPending}
        onRetry={() => void status.refetch()}
        rows={rows}
      />
    </div>
  );
}

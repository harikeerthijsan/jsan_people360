'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { useMyProjects } from '@/features/self-service/hooks';
import type { MyProject } from '@/features/self-service/types';

/**
 * My Projects.
 *
 * Read-only, and there is no action anywhere on this screen -- allocation is a
 * decision a manager makes, and offering an employee a button that would be
 * refused is worse than offering none.
 *
 * Past allocations are shown alongside current ones rather than hidden: "which
 * project was I on in March?" is the question this page is most often opened
 * for, and `is_current` is what separates the two.
 */
export function MyProjectsPage(): React.JSX.Element {
  const projects = useMyProjects();
  const rows = projects.data ?? [];
  const current = rows.filter((row) => row.is_current);

  const totalAllocation = current.reduce((sum, row) => sum + Number(row.allocation_percentage), 0);

  const columns: DataTableColumn<MyProject>[] = [
    {
      id: 'project',
      header: 'Project',
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{row.project_name}</p>
          <p className="text-muted-foreground truncate text-xs">{row.project_code}</p>
        </div>
      ),
    },
    { id: 'client', header: 'Client', cell: (row) => row.client_name ?? '—' },
    { id: 'role', header: 'My role', cell: (row) => row.role ?? '—' },
    {
      id: 'allocation',
      header: 'Allocation',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.allocation_percentage}%</span>,
    },
    {
      id: 'dates',
      header: 'From — to',
      cell: (row) => (
        <span className="tabular-nums">
          {row.start_date} → {row.end_date ?? 'ongoing'}
        </span>
      ),
    },
    {
      id: 'billable',
      header: 'Billing',
      cell: (row) => (
        <Badge variant={row.billable ? 'success' : 'outline'}>
          {row.billable ? 'Billable' : 'Non-billable'}
        </Badge>
      ),
    },
    {
      id: 'current',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.is_current ? 'default' : 'outline'}>{row.is_current ? 'Current' : 'Past'}</Badge>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Projects"
        description="Where your time is allocated. Only current allocations can be booked against on a timesheet."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Current projects" value={current.length} />
        <StatCard hint="across current projects" label="Allocated" value={`${String(totalAllocation)}%`} />
        <StatCard
          hint="billable right now"
          label="Billable"
          value={current.filter((row) => row.billable).length}
        />
      </div>

      <DataTable
        columns={columns}
        emptyDescription="You are not allocated to a project. Your manager assigns allocations."
        emptyTitle="No allocations"
        error={projects.error}
        getRowId={(row) => row.allocation_id}
        isLoading={projects.isPending}
        onRetry={() => void projects.refetch()}
        rows={rows}
      />
    </div>
  );
}

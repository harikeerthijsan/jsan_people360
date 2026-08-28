'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';
import { useHelpdeskDashboard, useTicketCategories, useTickets } from '@/features/helpdesk/hooks';
import {
  TICKET_PRIORITY_LABELS,
  TICKET_QUEUE_LABELS,
  TICKET_STATUS_LABELS,
  type Ticket,
  type TicketFilters,
  type TicketPriority,
  type TicketQueue,
  type TicketStatus,
} from '@/features/helpdesk/types';

/**
 * The desk.
 *
 * What an agent sees is narrowed on the server by the same scope that governs
 * every other list in the product: a manager holding `helpdesk:view` without
 * `employees:view_all` sees their team's requests, and an HR agent sees the
 * whole desk. Nothing on this screen widens that -- the filters below narrow a
 * result set the server has already decided.
 *
 * Filtering happens server-side and one page at a time. Pulling the whole desk
 * into the browser to filter it there would be the same mistake §21 of the
 * asset brief called out, and for the same reason.
 */

const STATUS_TONE: Record<TicketStatus, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  open: 'default',
  in_progress: 'default',
  waiting_on_employee: 'outline',
  resolved: 'secondary',
  closed: 'secondary',
  cancelled: 'outline',
  reopened: 'destructive',
};

const STATUSES: TicketStatus[] = [
  'open',
  'in_progress',
  'waiting_on_employee',
  'resolved',
  'closed',
  'cancelled',
  'reopened',
];
const PRIORITIES: TicketPriority[] = ['urgent', 'high', 'medium', 'low'];
const QUEUES: TicketQueue[] = ['hr', 'it', 'admin', 'finance', 'facilities'];

export function HelpdeskQueuePage(): React.JSX.Element {
  const router = useRouter();
  const categories = useTicketCategories();
  const dashboard = useHelpdeskDashboard();
  const [filters, setFilters] = React.useState<TicketFilters>({ page: 1, page_size: 20, open_only: true });

  /** Any filter change resets to page one; page 4 of a new result set is meaningless. */
  const set = <K extends keyof TicketFilters>(key: K, value: TicketFilters[K]): void =>
    setFilters((current) => ({ ...current, [key]: value, page: 1 }));

  const query = useTickets(filters);
  const rows = query.data?.items ?? [];
  const summary = dashboard.data;

  const columns: DataTableColumn<Ticket>[] = [
    {
      id: 'subject',
      header: 'Request',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.subject}</p>
          <p className="text-muted-foreground text-xs">
            {row.ticket_code} · {row.category.name}
          </p>
        </div>
      ),
    },
    {
      id: 'requester',
      header: 'Raised by',
      cell: (row) => (
        <div>
          <p className="text-sm">{(row.raised_for ?? row.raised_by).full_name}</p>
          {row.raised_for !== null ? (
            <p className="text-muted-foreground text-xs">logged by {row.raised_by.full_name}</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'queue',
      header: 'Queue',
      cell: (row) => <Badge variant="outline">{TICKET_QUEUE_LABELS[row.queue]}</Badge>,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant={STATUS_TONE[row.status]}>{TICKET_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'priority',
      header: 'Priority',
      cell: (row) => <Badge variant="outline">{TICKET_PRIORITY_LABELS[row.priority]}</Badge>,
    },
    {
      id: 'assignee',
      header: 'Owner',
      cell: (row) =>
        row.assigned_to_id === null ? (
          <span className="text-muted-foreground text-xs">Unassigned</span>
        ) : (
          <span className="text-xs">Assigned</span>
        ),
    },
    {
      id: 'due',
      header: 'Due',
      cell: (row) =>
        row.due_at === null ? (
          '—'
        ) : (
          <span className={row.is_overdue ? 'text-destructive font-medium' : ''}>
            {new Date(row.due_at).toLocaleDateString()}
          </span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Helpdesk"
        description="Requests from employees, in the queues you are responsible for."
      />

      {summary ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Open" value={summary.open_tickets} />
          <StatCard label="Unassigned" value={summary.unassigned} hint="Nobody has picked these up" />
          <StatCard label="Overdue" value={summary.overdue} hint="Past the category's response time" />
          <StatCard label="Waiting on employee" value={summary.waiting_on_employee} />
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-3">
        <SearchBar
          value={filters.search ?? ''}
          onChange={(value) => set('search', value === '' ? undefined : value)}
          placeholder="Search by code or subject"
          className="w-full sm:w-72"
        />

        <select
          aria-label="Status"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={filters.status ?? ''}
          onChange={(event) => set('status', (event.target.value || undefined) as TicketStatus | undefined)}
        >
          <option value="">Any status</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {TICKET_STATUS_LABELS[value]}
            </option>
          ))}
        </select>

        <select
          aria-label="Priority"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={filters.priority ?? ''}
          onChange={(event) =>
            set('priority', (event.target.value || undefined) as TicketPriority | undefined)
          }
        >
          <option value="">Any priority</option>
          {PRIORITIES.map((value) => (
            <option key={value} value={value}>
              {TICKET_PRIORITY_LABELS[value]}
            </option>
          ))}
        </select>

        <select
          aria-label="Queue"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={filters.queue ?? ''}
          onChange={(event) => set('queue', (event.target.value || undefined) as TicketQueue | undefined)}
        >
          <option value="">Any queue</option>
          {QUEUES.map((value) => (
            <option key={value} value={value}>
              {TICKET_QUEUE_LABELS[value]}
            </option>
          ))}
        </select>

        <select
          aria-label="Category"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={filters.category_id ?? ''}
          onChange={(event) => set('category_id', event.target.value || undefined)}
        >
          <option value="">Any category</option>
          {(categories.data ?? []).map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>

        <Button
          variant={filters.unassigned === true ? 'default' : 'outline'}
          size="sm"
          onClick={() => set('unassigned', filters.unassigned === true ? undefined : true)}
        >
          Unassigned
        </Button>
        <Button
          variant={filters.overdue === true ? 'default' : 'outline'}
          size="sm"
          onClick={() => set('overdue', filters.overdue === true ? undefined : true)}
        >
          Overdue
        </Button>
        <Button
          variant={filters.open_only === true ? 'default' : 'outline'}
          size="sm"
          onClick={() => set('open_only', filters.open_only === true ? undefined : true)}
        >
          Open only
        </Button>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        onRowClick={(row) => router.push(routes.helpdeskTicket(row.id))}
        emptyTitle="No requests"
        emptyDescription="Nothing matches these filters. Clear one and try again."
      />

      {query.data ? (
        <Pagination
          meta={query.data.meta}
          onPageChange={(page) => setFilters((current) => ({ ...current, page }))}
          itemLabel="requests"
          disabled={query.isFetching}
        />
      ) : null}
    </div>
  );
}

'use client';

import {
  ArchiveRestore,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  MinusCircle,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';

import { ActionMenu, type ActionMenuItem } from '@/components/common/action-menu';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmploymentStatusBadge } from '@/components/common/employment-status-badge';
import { ConfirmDialog } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { UserIdentity } from '@/components/common/user-avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  useEmployeeList,
  useExportEmployees,
  useSimpleAction,
} from '@/features/employees/hooks/use-employees';
import {
  EMPLOYMENT_STATUSES,
  EMPLOYMENT_STATUS_LABELS,
  type EmployeeListQuery,
  type EmployeeRecord,
  type EmploymentStatus,
} from '@/features/employees/types/employee.types';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import {
  MASTER_VIEW_OPTIONS,
  useMasterListState,
  type MasterView,
} from '@/features/organization/hooks/use-master-list-state';
import { useDisclosure } from '@/hooks/use-disclosure';
import { formatDate } from '@/lib/utils';

const BASE_PATH = '/employees';

/** The advanced filters, and the query parameter each is stored in. */
const ADVANCED_FILTERS = [
  { param: 'team', field: 'team_id', label: 'Team', master: 'teams' },
  { param: 'designation', field: 'designation_id', label: 'Designation', master: 'designations' },
  { param: 'location', field: 'work_location_id', label: 'Work location', master: 'locations' },
  { param: 'grade', field: 'grade_id', label: 'Grade', master: 'grades' },
] as const;

/** The employee directory. */
export function EmployeeListPage(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();

  // The shared list-state hook gives the same URL contract, debounce and
  // reset-to-page-one behaviour as every other list screen.
  const state = useMasterListState('employee_code');
  const advanced = useDisclosure(false);

  /** Read one advanced filter out of the URL. */
  const filterValue = React.useCallback((param: string) => searchParams.get(param) ?? '', [searchParams]);

  const setParam = React.useCallback(
    (param: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) params.set(param, value);
      else params.delete(param);
      // Any filter change invalidates the current page number.
      params.delete('page');
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const statusFilter = filterValue('status') as EmploymentStatus | '';

  const query: EmployeeListQuery = React.useMemo(() => {
    const base: EmployeeListQuery = {
      page: state.query.page,
      page_size: state.query.page_size,
      archived: state.query.archived,
      sort_by: state.sortBy,
      sort_order: state.sortOrder,
    };

    if (state.query.search) base.search = state.query.search;
    if (statusFilter) base.employment_status = statusFilter;
    for (const filter of ADVANCED_FILTERS) {
      const value = filterValue(filter.param);
      if (value) base[filter.field] = value;
    }
    return base;
  }, [filterValue, state.query, state.sortBy, state.sortOrder, statusFilter]);

  const listQuery = useEmployeeList(query);
  const exportEmployees = useExportEmployees();

  const activate = useSimpleAction('activate');
  const deactivate = useSimpleAction('deactivate');
  const archive = useSimpleAction('archive');
  const restore = useSimpleAction('restore');

  const confirm = useDisclosure(false);
  const [pending, setPending] = React.useState<EmployeeRecord | null>(null);

  const requestArchive = React.useCallback(
    (employee: EmployeeRecord) => {
      setPending(employee);
      confirm.open();
    },
    [confirm],
  );

  const columns = React.useMemo<DataTableColumn<EmployeeRecord>[]>(
    () => [
      {
        id: 'name',
        header: 'Employee',
        sortKey: 'first_name',
        cell: (row) => (
          <UserIdentity name={row.full_name} secondary={row.official_email} photoUrl={row.photo_url} />
        ),
      },
      {
        id: 'employee_code',
        header: 'Employee ID',
        sortKey: 'employee_code',
        className: 'w-32',
        cell: (row) => <span className="font-mono text-xs">{row.employee_code}</span>,
      },
      {
        id: 'placement',
        header: 'Team',
        className: 'w-52',
        cell: (row) => {
          const team = row.organization.team;
          const designation = row.organization.designation;
          if (!team && !designation) return <span className="text-muted-foreground">—</span>;
          return (
            <div className="min-w-0">
              <p className="truncate">{team?.name ?? '—'}</p>
              {designation ? (
                <p className="text-muted-foreground truncate text-xs">{designation.name}</p>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'joining_date',
        header: 'Joined',
        sortKey: 'joining_date',
        className: 'w-32',
        cell: (row) => formatDate(row.joining_date),
      },
      {
        id: 'status',
        header: 'Status',
        align: 'right',
        className: 'w-36',
        cell: (row) => (
          <EmploymentStatusBadge status={row.employment_status} archived={row.deleted_at !== null} />
        ),
      },
      {
        id: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        className: 'w-16',
        cell: (row) => {
          const isArchived = row.deleted_at !== null;
          const isInactive = row.employment_status === 'inactive';

          const items: ActionMenuItem[] = [
            { id: 'view', label: 'View profile', href: `${BASE_PATH}/${row.id}` },
            {
              id: 'edit',
              label: 'Edit',
              icon: Pencil,
              href: `${BASE_PATH}/${row.id}/edit`,
              hidden: isArchived,
            },
            {
              id: 'deactivate',
              label: 'Deactivate',
              icon: MinusCircle,
              separatorBefore: true,
              hidden: isArchived || isInactive,
              onSelect: () => {
                deactivate.mutate(row.id);
              },
            },
            {
              id: 'activate',
              label: 'Activate',
              icon: CheckCircle2,
              separatorBefore: true,
              hidden: isArchived || !isInactive,
              onSelect: () => {
                activate.mutate(row.id);
              },
            },
            {
              id: 'archive',
              label: 'Archive',
              icon: Trash2,
              destructive: true,
              hidden: isArchived,
              onSelect: () => {
                requestArchive(row);
              },
            },
            {
              id: 'restore',
              label: 'Restore',
              icon: ArchiveRestore,
              hidden: !isArchived,
              onSelect: () => {
                restore.mutate(row.id);
              },
            },
          ];

          return <ActionMenu items={items} label={`Actions for ${row.full_name}`} />;
        },
      },
    ],
    [activate, deactivate, requestArchive, restore],
  );

  const page = listQuery.data;
  const hasAdvancedFilter = ADVANCED_FILTERS.some((filter) => filterValue(filter.param) !== '');
  const isFiltered = state.isFiltered || statusFilter !== '' || hasAdvancedFilter;

  const clearAll = React.useCallback(() => {
    router.replace(BASE_PATH, { scroll: false });
  }, [router]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        description="The single source of truth for everyone the organization employs."
        actions={
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" isLoading={exportEmployees.isPending}>
                  <Download aria-hidden="true" />
                  Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => {
                    exportEmployees.mutate({ query, format: 'csv' });
                  }}
                >
                  <FileSpreadsheet aria-hidden="true" />
                  Export as CSV
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => {
                    exportEmployees.mutate({ query, format: 'xlsx' });
                  }}
                >
                  <FileSpreadsheet aria-hidden="true" />
                  Export as Excel
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button asChild>
              <Link href={`${BASE_PATH}/new`}>
                <Plus aria-hidden="true" />
                New employee
              </Link>
            </Button>
          </div>
        }
      />

      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar
            value={state.search}
            onChange={state.setSearch}
            placeholder="Search employee ID, name, email or mobile…"
            label="Search employees"
          />

          <div className="flex items-center gap-2">
            <Select
              value={statusFilter === '' ? 'all' : statusFilter}
              onValueChange={(value) => {
                setParam('status', value === 'all' ? '' : value);
              }}
            >
              <SelectTrigger className="w-40" aria-label="Filter by employment status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {EMPLOYMENT_STATUSES.map((status) => (
                  <SelectItem key={status} value={status}>
                    {EMPLOYMENT_STATUS_LABELS[status]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={state.view}
              onValueChange={(value) => {
                state.setView(value as MasterView);
              }}
            >
              <SelectTrigger className="w-36" aria-label="Filter by record state">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MASTER_VIEW_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              variant={hasAdvancedFilter ? 'secondary' : 'ghost'}
              size="sm"
              onClick={advanced.toggle}
              aria-expanded={advanced.isOpen}
            >
              <SlidersHorizontal aria-hidden="true" />
              Filters
            </Button>

            {isFiltered ? (
              <Button variant="ghost" size="sm" onClick={clearAll}>
                Clear
              </Button>
            ) : null}
          </div>
        </div>

        {advanced.isOpen ? (
          <div className="bg-muted/40 grid gap-3 rounded-md border p-4 sm:grid-cols-2 lg:grid-cols-4">
            {ADVANCED_FILTERS.map((filter) => (
              <AdvancedFilter
                key={filter.param}
                label={filter.label}
                master={filter.master}
                value={filterValue(filter.param)}
                onChange={(value) => {
                  setParam(filter.param, value);
                }}
              />
            ))}
          </div>
        ) : null}
      </div>

      <DataTable
        columns={columns}
        rows={page?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={listQuery.isPending}
        error={listQuery.error}
        onRetry={() => {
          void listQuery.refetch();
        }}
        onRowClick={(row) => {
          router.push(`${BASE_PATH}/${row.id}`);
        }}
        sort={{ sortBy: state.sortBy, sortOrder: state.sortOrder }}
        onSortChange={state.setSort}
        caption="Employee directory"
        emptyTitle={isFiltered ? 'No employees match your filters' : 'No employees yet'}
        emptyDescription={
          isFiltered
            ? 'Try a different search term, or clear the filters to see everyone.'
            : 'Record the first employee to get started.'
        }
        emptyAction={
          isFiltered
            ? { label: 'Clear filters', onClick: clearAll }
            : {
                label: 'Create an employee',
                onClick: () => {
                  router.push(`${BASE_PATH}/new`);
                },
              }
        }
      />

      {page ? (
        <Pagination
          meta={page.meta}
          onPageChange={state.setPage}
          itemLabel="employees"
          disabled={listQuery.isFetching}
        />
      ) : null}

      <ConfirmDialog
        open={confirm.isOpen}
        onOpenChange={confirm.setOpen}
        title="Archive this employee?"
        description={
          pending
            ? `${pending.full_name} (${pending.employee_code}) will be hidden from the directory. Their employment history is kept in full, and you can restore the record at any time.`
            : ''
        }
        confirmLabel="Archive"
        destructive
        isConfirming={archive.isPending}
        onConfirm={() => {
          if (!pending) return;
          archive.mutate(pending.id, {
            onSettled: () => {
              confirm.close();
              setPending(null);
            },
          });
        }}
      />
    </div>
  );
}

/** One master-backed picker in the advanced filter panel. */
function AdvancedFilter({
  label,
  master,
  value,
  onChange,
}: {
  label: string;
  master: 'teams' | 'designations' | 'locations' | 'grades';
  value: string;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const query = useMasterOptions(master);

  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-medium" htmlFor={`filter-${master}`}>
        {label}
      </label>
      <Select
        value={value === '' ? 'all' : value}
        onValueChange={(next) => {
          onChange(next === 'all' ? '' : next);
        }}
      >
        <SelectTrigger id={`filter-${master}`} className="w-full">
          <SelectValue placeholder={`All ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All {label.toLowerCase()}</SelectItem>
          {(query.data?.items ?? []).map((record) => (
            <SelectItem key={record.id} value={record.id}>
              {record.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

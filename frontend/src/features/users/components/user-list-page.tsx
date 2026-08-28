'use client';

import { ArchiveRestore, CheckCircle2, KeyRound, MinusCircle, Pencil, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { ActionMenu, type ActionMenuItem } from '@/components/common/action-menu';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ConfirmDialog } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { StatusBadge } from '@/components/common/status-badge';
import { UserIdentity } from '@/components/common/user-avatar';
import { useAuth } from '@/components/providers/auth-provider';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  MASTER_VIEW_OPTIONS,
  useMasterListState,
  type MasterView,
} from '@/features/organization/hooks/use-master-list-state';
import { useUserLifecycleAction, useUserList } from '@/features/users/hooks/use-users';
import type { UserListQuery, UserRecord } from '@/features/users/types/user.types';
import { useDisclosure } from '@/hooks/use-disclosure';
import { formatDate } from '@/lib/utils';

const BASE_PATH = '/users';

/** The user directory. */
export function UserListPage(): React.JSX.Element {
  const router = useRouter();
  const { user: currentUser } = useAuth();

  // The list state hook is shared with the master screens: same URL contract,
  // same debounce, same reset-to-page-one behaviour.
  const state = useMasterListState('first_name');
  const query: UserListQuery = React.useMemo(
    () => ({ ...state.query, sort_by: state.sortBy, sort_order: state.sortOrder }),
    [state.query, state.sortBy, state.sortOrder],
  );
  const listQuery = useUserList(query);

  const deactivate = useUserLifecycleAction('deactivate');
  const activate = useUserLifecycleAction('activate');
  const archive = useUserLifecycleAction('archive');
  const restore = useUserLifecycleAction('restore');

  const confirm = useDisclosure(false);
  const [pending, setPending] = React.useState<UserRecord | null>(null);

  const requestArchive = React.useCallback(
    (user: UserRecord) => {
      setPending(user);
      confirm.open();
    },
    [confirm],
  );

  const columns = React.useMemo<DataTableColumn<UserRecord>[]>(
    () => [
      {
        id: 'name',
        header: 'User',
        sortKey: 'first_name',
        cell: (row) => <UserIdentity name={row.full_name} secondary={row.email} photoUrl={row.avatar_url} />,
      },
      {
        id: 'user_code',
        header: 'Staff code',
        sortKey: 'user_code',
        className: 'w-32',
        cell: (row) => <span className="font-mono text-xs">{row.user_code}</span>,
      },
      {
        id: 'username',
        header: 'Username',
        sortKey: 'username',
        className: 'w-40',
        cell: (row) => <span className="font-mono text-xs">{row.username}</span>,
      },
      {
        id: 'placement',
        header: 'Business unit',
        className: 'w-52',
        cell: (row) => {
          const businessUnit = row.organization.business_unit;
          const designation = row.organization.designation;
          if (!businessUnit && !designation) return <span className="text-muted-foreground">—</span>;
          return (
            <div className="min-w-0">
              <p className="truncate">{businessUnit?.name ?? '—'}</p>
              {designation ? (
                <p className="text-muted-foreground truncate text-xs">{designation.name}</p>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'last_login',
        header: 'Last sign-in',
        sortKey: 'last_login_at',
        className: 'w-36',
        cell: (row) =>
          row.last_login_at ? (
            formatDate(row.last_login_at)
          ) : (
            <span className="text-muted-foreground">Never</span>
          ),
      },
      {
        id: 'status',
        header: 'Status',
        align: 'right',
        className: 'w-32',
        cell: (row) => <StatusBadge status={row.status} archived={row.deleted_at !== null} />,
      },
      {
        id: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        className: 'w-16',
        cell: (row) => {
          const isSelf = currentUser?.id === row.id;
          const isArchived = row.deleted_at !== null;

          const items: ActionMenuItem[] = [
            { id: 'view', label: 'View details', href: `${BASE_PATH}/${row.id}` },
            {
              id: 'edit',
              label: 'Edit',
              icon: Pencil,
              href: `${BASE_PATH}/${row.id}/edit`,
              hidden: isArchived,
            },
            {
              id: 'reset',
              label: 'Reset password',
              icon: KeyRound,
              href: `${BASE_PATH}/${row.id}?reset=1`,
              hidden: isArchived,
            },
            {
              id: 'deactivate',
              label: 'Deactivate',
              icon: MinusCircle,
              separatorBefore: true,
              hidden: isArchived || !row.is_active,
              // Deactivating yourself would lock you out; the API refuses it
              // too, but disabling here explains why before the click.
              disabled: isSelf,
              onSelect: () => {
                deactivate.mutate(row.id);
              },
            },
            {
              id: 'activate',
              label: 'Activate',
              icon: CheckCircle2,
              separatorBefore: true,
              hidden: isArchived || row.is_active,
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
              disabled: isSelf,
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
    [activate, currentUser?.id, deactivate, requestArchive, restore],
  );

  const page = listQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users"
        description="Everyone with access to the platform. Accounts link to employee records in a later module."
        actions={
          <Button asChild>
            <Link href={`${BASE_PATH}/new`}>
              <Plus aria-hidden="true" />
              New user
            </Link>
          </Button>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBar
          value={state.search}
          onChange={state.setSearch}
          placeholder="Search name, staff code, username or email…"
          label="Search users"
        />

        <div className="flex items-center gap-2">
          <Select
            value={state.view}
            onValueChange={(value) => {
              state.setView(value as MasterView);
            }}
          >
            <SelectTrigger className="w-44" aria-label="Filter by status">
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

          {state.isFiltered ? (
            <Button variant="ghost" size="sm" onClick={state.reset}>
              Clear
            </Button>
          ) : null}
        </div>
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
        caption="User directory"
        emptyTitle={state.isFiltered ? 'No users match your filters' : 'No users yet'}
        emptyDescription={
          state.isFiltered
            ? 'Try a different search term, or clear the filters to see everyone.'
            : 'Create the first account to get started.'
        }
        emptyAction={
          state.isFiltered
            ? { label: 'Clear filters', onClick: state.reset }
            : {
                label: 'Create a user',
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
          itemLabel="users"
          disabled={listQuery.isFetching}
        />
      ) : null}

      <ConfirmDialog
        open={confirm.isOpen}
        onOpenChange={confirm.setOpen}
        title="Archive this user?"
        description={
          pending
            ? `${pending.full_name} (${pending.user_code}) will lose access immediately and every active session will end. Records that reference them are unaffected, and you can restore the account at any time.`
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

'use client';

import { ArchiveRestore, Pencil, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { ActionMenu, type ActionMenuItem } from '@/components/common/action-menu';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useDisclosure } from '@/hooks/use-disclosure';
import { MASTER_REGISTRY, type MasterConfig } from '@/features/organization/config/master-registry';
import {
  MASTER_VIEW_OPTIONS,
  useMasterListState,
  type MasterView,
} from '@/features/organization/hooks/use-master-list-state';
import { useArchiveMaster, useMasterList, useRestoreMaster } from '@/features/organization/hooks/use-masters';
import type { MasterRecord, MasterSlug } from '@/features/organization/types/organization.types';

interface MasterListPageProps {
  /**
   * The master to render.
   *
   * A slug rather than the config object: the route is a Server Component, and
   * the config holds cell renderers and mappers, which cannot be serialised
   * across the server/client boundary. Resolving it here keeps the boundary to
   * a plain string.
   */
  slug: MasterSlug;
}

/**
 * The list screen for every master.
 *
 * Search, filter, sort and page state live in the URL; the row actions and all
 * four display states come from the shared components. The only per-master
 * input is the config.
 */
export function MasterListPage({ slug }: MasterListPageProps): React.JSX.Element {
  const config: MasterConfig = MASTER_REGISTRY[slug];
  const router = useRouter();
  const state = useMasterListState(config.defaultSortBy);
  const listQuery = useMasterList(config.slug, state.query);

  const archive = useArchiveMaster(config.slug, config.label);
  const restore = useRestoreMaster(config.slug, config.label);

  const confirm = useDisclosure(false);
  const [pendingRecord, setPendingRecord] = React.useState<MasterRecord | null>(null);

  const basePath = `/organization/${config.slug}`;

  const requestArchive = React.useCallback(
    (record: MasterRecord) => {
      setPendingRecord(record);
      confirm.open();
    },
    [confirm],
  );

  const confirmArchive = React.useCallback(() => {
    if (!pendingRecord) return;
    archive.mutate(pendingRecord.id, {
      onSettled: () => {
        confirm.close();
        setPendingRecord(null);
      },
    });
  }, [archive, confirm, pendingRecord]);

  // The actions column is appended here rather than declared in the registry:
  // it is identical for every master and needs handlers the config cannot hold.
  const columns = React.useMemo<DataTableColumn<MasterRecord>[]>(
    () => [
      ...config.columns,
      {
        id: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        className: 'w-16',
        // Uses the shared ActionMenu rather than its own dropdown: the markup
        // was identical, and keeping a second copy meant a fix to one of them
        // (the dialog dismissal above) had to be remembered twice.
        cell: (row) => {
          const isArchived = row.deleted_at !== null;

          const items: ActionMenuItem[] = [
            { id: 'view', label: 'View details', href: `${basePath}/${row.id}` },
            {
              id: 'edit',
              label: 'Edit',
              icon: Pencil,
              href: `${basePath}/${row.id}/edit`,
              hidden: isArchived,
            },
            {
              id: 'archive',
              label: 'Archive',
              icon: Trash2,
              destructive: true,
              separatorBefore: true,
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

          return <ActionMenu items={items} label={`Actions for ${row.name}`} />;
        },
      },
    ],
    [basePath, config.columns, requestArchive, restore],
  );

  const page = listQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={config.labelPlural}
        description={config.blurb}
        actions={
          <Button asChild>
            <Link href={`${basePath}/new`}>
              <Plus aria-hidden="true" />
              New {config.label.toLowerCase()}
            </Link>
          </Button>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBar
          value={state.search}
          onChange={state.setSearch}
          placeholder={`Search ${config.labelPlural.toLowerCase()}…`}
          label={`Search ${config.labelPlural.toLowerCase()}`}
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
          router.push(`${basePath}/${row.id}`);
        }}
        sort={{ sortBy: state.sortBy, sortOrder: state.sortOrder }}
        onSortChange={state.setSort}
        caption={`${config.labelPlural} list`}
        emptyTitle={
          state.isFiltered
            ? `No ${config.labelPlural.toLowerCase()} match your filters`
            : `No ${config.labelPlural.toLowerCase()} yet`
        }
        emptyDescription={
          state.isFiltered
            ? 'Try a different search term, or clear the filters to see everything.'
            : config.blurb
        }
        emptyAction={
          state.isFiltered
            ? { label: 'Clear filters', onClick: state.reset }
            : {
                label: `Create the first ${config.label.toLowerCase()}`,
                onClick: () => {
                  router.push(`${basePath}/new`);
                },
              }
        }
      />

      {page ? (
        <Pagination
          meta={page.meta}
          onPageChange={state.setPage}
          itemLabel={config.labelPlural.toLowerCase()}
          disabled={listQuery.isFetching}
        />
      ) : null}

      <ConfirmDialog
        open={confirm.isOpen}
        onOpenChange={confirm.setOpen}
        title={`Archive this ${config.label.toLowerCase()}?`}
        description={
          pendingRecord
            ? `"${pendingRecord.name}" will be hidden from new selections. Existing records that reference it keep working, and you can restore it at any time.`
            : ''
        }
        confirmLabel="Archive"
        destructive
        isConfirming={archive.isPending}
        onConfirm={confirmArchive}
      />
    </div>
  );
}

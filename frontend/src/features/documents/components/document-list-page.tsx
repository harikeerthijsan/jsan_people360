'use client';

import { ArchiveRestore, Download, Eye, Plus, SlidersHorizontal, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';

import { ActionMenu, type ActionMenuItem } from '@/components/common/action-menu';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { DocumentStatusBadge, ExpiryBadge } from '@/components/common/document-status-badge';
import { ConfirmDialog } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  useDocumentAction,
  useDocumentCategories,
  useDocumentList,
  useDocumentTypes,
  useDownloadDocument,
} from '@/features/documents/hooks/use-documents';
import { useOwnerOptions } from '@/features/documents/hooks/use-owner-options';
import {
  DOCUMENT_STATUS_LABELS,
  EXPIRY_STATE_LABELS,
  FILTERABLE_DOCUMENT_STATUSES,
  OWNER_TYPE_LABELS,
  type DocumentOwnerType,
  type DocumentListQuery,
  type DocumentRecord,
  type DocumentStatus,
  type ExpiryState,
} from '@/features/documents/types/document.types';
import {
  MASTER_VIEW_OPTIONS,
  useMasterListState,
  type MasterView,
} from '@/features/organization/hooks/use-master-list-state';
import { useDisclosure } from '@/hooks/use-disclosure';
import { formatDate } from '@/lib/utils';

const BASE_PATH = '/documents';

/** The expiry states worth filtering by. "none" is a non-answer, so it is left out. */
const EXPIRY_FILTERS: ExpiryState[] = ['expired', 'expiring_soon', 'valid'];
const OWNER_TYPES: DocumentOwnerType[] = ['employee', 'organization', 'user', 'candidate'];

export function DocumentListPage(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();

  const state = useMasterListState('created_at');
  const advanced = useDisclosure(false);

  const paramValue = React.useCallback((name: string) => searchParams.get(name) ?? '', [searchParams]);

  /**
   * Apply several filter changes as one navigation.
   *
   * Calling a single-parameter setter twice in the same handler does not work:
   * both calls build their URL from the same `searchParams` snapshot, so the
   * second replaces the first rather than adding to it. Dependent filters —
   * choosing a category clears the type, choosing an owner type clears the
   * owner — always change two parameters at once, so the multi-value form is
   * the primitive and the single-value one is built from it.
   */
  const setParams = React.useCallback(
    (changes: Record<string, string>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [name, value] of Object.entries(changes)) {
        if (value) params.set(name, value);
        else params.delete(name);
      }
      // Any filter change invalidates the page number.
      params.delete('page');
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const setParam = React.useCallback(
    (name: string, value: string) => {
      setParams({ [name]: value });
    },
    [setParams],
  );

  const statusFilter = paramValue('status') as DocumentStatus | '';
  const categoryFilter = paramValue('category');
  const typeFilter = paramValue('type');
  const expiryFilter = paramValue('expiry') as ExpiryState | '';
  const ownerTypeFilter = paramValue('owner_type') as DocumentOwnerType | '';
  const ownerIdFilter = paramValue('owner_id');

  // Filtering by owner used to mean pasting a UUID, which nobody has to hand.
  const ownerOptions = useOwnerOptions(ownerTypeFilter === '' ? undefined : ownerTypeFilter);
  const uploadedFrom = paramValue('uploaded_from');
  const uploadedTo = paramValue('uploaded_to');

  const query: DocumentListQuery = React.useMemo(() => {
    const base: DocumentListQuery = {
      page: state.query.page,
      page_size: state.query.page_size,
      archived: state.query.archived,
      sort_by: state.sortBy,
      sort_order: state.sortOrder,
    };

    if (state.query.search) base.search = state.query.search;
    if (statusFilter) base.status = statusFilter;
    if (categoryFilter) base.category_id = categoryFilter;
    if (typeFilter) base.document_type_id = typeFilter;
    if (expiryFilter) base.expiry_state = expiryFilter;
    if (ownerTypeFilter) base.owner_type = ownerTypeFilter;
    if (ownerIdFilter) base.owner_id = ownerIdFilter;
    if (uploadedFrom) base.uploaded_from = uploadedFrom;
    if (uploadedTo) base.uploaded_to = uploadedTo;
    return base;
  }, [
    categoryFilter,
    expiryFilter,
    ownerIdFilter,
    ownerTypeFilter,
    state.query,
    state.sortBy,
    state.sortOrder,
    statusFilter,
    typeFilter,
    uploadedFrom,
    uploadedTo,
  ]);

  const listQuery = useDocumentList(query);
  const categories = useDocumentCategories();
  // Types are scoped to the chosen category: offering every type regardless
  // would make the picker long and most of it irrelevant.
  const types = useDocumentTypes(categoryFilter || undefined);

  const archive = useDocumentAction('archive');
  const restore = useDocumentAction('restore');
  const download = useDownloadDocument();

  const confirm = useDisclosure(false);
  const [pending, setPending] = React.useState<DocumentRecord | null>(null);

  const requestArchive = React.useCallback(
    (document: DocumentRecord) => {
      setPending(document);
      confirm.open();
    },
    [confirm],
  );

  const columns = React.useMemo<DataTableColumn<DocumentRecord>[]>(
    () => [
      {
        id: 'name',
        header: 'Document',
        sortKey: 'name',
        cell: (row) => (
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="text-muted-foreground truncate font-mono text-xs">{row.document_code}</p>
          </div>
        ),
      },
      {
        id: 'type',
        header: 'Type',
        className: 'w-48',
        cell: (row) => (
          <div className="min-w-0">
            <p className="truncate">{row.document_type?.name ?? '—'}</p>
            {row.category ? (
              <p className="text-muted-foreground truncate text-xs">{row.category.name}</p>
            ) : null}
          </div>
        ),
      },
      {
        id: 'owner',
        header: 'Belongs to',
        className: 'w-44',
        cell: (row) => {
          if (!row.owner?.display_name) {
            return <span className="text-muted-foreground">—</span>;
          }
          return (
            <div className="min-w-0">
              <p className="truncate">{row.owner.display_name}</p>
              {row.owner.reference_code ? (
                <p className="text-muted-foreground truncate font-mono text-xs">{row.owner.reference_code}</p>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'expiry',
        header: 'Expiry',
        sortKey: 'expiry_date',
        className: 'w-40',
        cell: (row) =>
          row.expiry_date ? (
            <ExpiryBadge state={row.expiry_state} detail={formatDate(row.expiry_date)} />
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'status',
        header: 'Status',
        align: 'right',
        className: 'w-36',
        cell: (row) => <DocumentStatusBadge status={row.status} archived={row.deleted_at !== null} />,
      },
      {
        id: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        className: 'w-16',
        cell: (row) => {
          const isArchived = row.deleted_at !== null;
          const version = row.current_version;

          const items: ActionMenuItem[] = [
            { id: 'view', label: 'View details', href: `${BASE_PATH}/${row.id}`, icon: Eye },
            {
              id: 'download',
              label: 'Download',
              icon: Download,
              hidden: version === null,
              onSelect: () => {
                if (!version) return;
                download.mutate({ id: row.id, filename: version.original_filename });
              },
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
    [download, requestArchive, restore],
  );

  const page = listQuery.data;
  const hasAdvanced = Boolean(
    categoryFilter ||
    typeFilter ||
    expiryFilter ||
    ownerTypeFilter ||
    ownerIdFilter ||
    uploadedFrom ||
    uploadedTo,
  );
  const isFiltered = state.isFiltered || statusFilter !== '' || hasAdvanced;

  const clearAll = React.useCallback(() => {
    router.replace(BASE_PATH, { scroll: false });
  }, [router]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="The shared vault. Every module files its documents here."
        actions={
          <Button asChild>
            <Link href={`${BASE_PATH}/upload`}>
              <Plus aria-hidden="true" />
              Upload document
            </Link>
          </Button>
        }
      />

      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar
            value={state.search}
            onChange={state.setSearch}
            placeholder="Search document ID, name or description…"
            label="Search documents"
          />

          <div className="flex items-center gap-2">
            <Select
              value={statusFilter === '' ? 'all' : statusFilter}
              onValueChange={(value) => {
                setParam('status', value === 'all' ? '' : value);
              }}
            >
              <SelectTrigger className="w-40" aria-label="Filter by status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {FILTERABLE_DOCUMENT_STATUSES.map((status) => (
                  <SelectItem key={status} value={status}>
                    {DOCUMENT_STATUS_LABELS[status]}
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
              variant={hasAdvanced ? 'secondary' : 'ghost'}
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
          <div className="bg-muted/40 grid gap-3 rounded-md border p-4 sm:grid-cols-3">
            <FilterSelect
              id="filter-category"
              label="Category"
              value={categoryFilter}
              options={(categories.data?.items ?? []).map((item) => ({
                value: item.id,
                label: item.name,
              }))}
              onChange={(value) => {
                // The chosen type may not belong to the new category, so both
                // change together.
                setParams({ category: value, type: '' });
              }}
            />
            <FilterSelect
              id="filter-type"
              label="Document type"
              allLabel="All document types"
              value={typeFilter}
              options={(types.data?.items ?? []).map((item) => ({
                value: item.id,
                label: item.name,
              }))}
              onChange={(value) => {
                setParam('type', value);
              }}
            />
            <FilterSelect
              id="filter-expiry"
              label="Expiry"
              value={expiryFilter}
              options={EXPIRY_FILTERS.map((state_) => ({
                value: state_,
                label: EXPIRY_STATE_LABELS[state_],
              }))}
              onChange={(value) => {
                setParam('expiry', value);
              }}
            />
            <FilterSelect
              id="filter-owner-type"
              label="Owner type"
              allLabel="All owner types"
              value={ownerTypeFilter}
              options={OWNER_TYPES.map((ownerType) => ({
                value: ownerType,
                label: OWNER_TYPE_LABELS[ownerType],
              }))}
              onChange={(value) => {
                // The chosen owner belongs to the previous type's list.
                setParams({ owner_type: value, owner_id: '' });
              }}
            />
            <FilterSelect
              id="filter-owner"
              label="Owner"
              allLabel="All owners"
              value={ownerIdFilter}
              options={ownerOptions.options}
              disabled={ownerTypeFilter === ''}
              placeholder={ownerTypeFilter === '' ? 'Choose an owner type first' : undefined}
              onChange={(value) => setParam('owner_id', value)}
            />
            <FilterInput
              id="filter-uploaded-from"
              label="Uploaded from"
              type="date"
              value={uploadedFrom}
              onChange={(value) => setParam('uploaded_from', value)}
            />
            <FilterInput
              id="filter-uploaded-to"
              label="Uploaded to"
              type="date"
              value={uploadedTo}
              onChange={(value) => setParam('uploaded_to', value)}
            />
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
        caption="Document vault"
        emptyTitle={isFiltered ? 'No documents match your filters' : 'No documents yet'}
        emptyDescription={
          isFiltered
            ? 'Try a different search term, or clear the filters to see everything.'
            : 'Upload the first document to get started.'
        }
        emptyAction={
          isFiltered
            ? { label: 'Clear filters', onClick: clearAll }
            : {
                label: 'Upload a document',
                onClick: () => {
                  router.push(`${BASE_PATH}/upload`);
                },
              }
        }
      />

      {page ? (
        <Pagination
          meta={page.meta}
          onPageChange={state.setPage}
          itemLabel="documents"
          disabled={listQuery.isFetching}
        />
      ) : null}

      <ConfirmDialog
        open={confirm.isOpen}
        onOpenChange={confirm.setOpen}
        title="Archive this document?"
        description={
          pending
            ? `"${pending.name}" will be hidden from the vault. Every version is kept, nothing is deleted from storage, and you can restore it at any time.`
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

function FilterInput({
  id,
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
}): React.JSX.Element {
  const [draft, setDraft] = React.useState(value);
  React.useEffect(() => setDraft(value), [value]);
  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-medium" htmlFor={id}>
        {label}
      </label>
      <Input
        id={id}
        type={type}
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => onChange(draft)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onChange(draft);
        }}
      />
    </div>
  );
}

/** One labelled select in the advanced filter panel. */
function FilterSelect({
  id,
  label,
  value,
  options,
  onChange,
  disabled = false,
  placeholder,
  allLabel,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
  /** Overrides the "All …" prompt when the field is not yet usable. */
  placeholder?: string;
  /** The "no filter" option. Spelled out where the plural is not label + "s". */
  allLabel?: string;
}): React.JSX.Element {
  const anyOption = allLabel ?? `All ${label.toLowerCase()}`;
  return (
    <div className="space-y-1.5">
      <label className="text-muted-foreground text-xs font-medium" htmlFor={id}>
        {label}
      </label>
      <Select
        value={value === '' ? 'all' : value}
        disabled={disabled}
        onValueChange={(next) => {
          onChange(next === 'all' ? '' : next);
        }}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={placeholder ?? anyOption} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{anyOption}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

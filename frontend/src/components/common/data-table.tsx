'use client';

import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { TableSkeleton } from '@/components/common/loading-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';

export interface DataTableColumn<TRow> {
  /** Stable key, also used as the React key for cells. */
  id: string;
  header: React.ReactNode;
  /** Renders the cell body for a row. */
  cell: (row: TRow) => React.ReactNode;
  /** Extra classes applied to both the header and body cells. */
  className?: string;
  /** Right-align numeric columns. */
  align?: 'left' | 'right' | 'center';
  /**
   * Server-side sort key. Present means the header is a sort control; the
   * value is sent to the API, so it must be a column the API accepts.
   */
  sortKey?: string;
}

export type SortOrder = 'asc' | 'desc';

export interface SortState {
  sortBy: string;
  sortOrder: SortOrder;
}

interface DataTableProps<TRow> {
  columns: DataTableColumn<TRow>[];
  rows: TRow[];
  /** Stable identity for each row. */
  getRowId: (row: TRow) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  onRowClick?: (row: TRow) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: { label: string; onClick: () => void };
  caption?: string;
  className?: string;
  /**
   * Render without the card surface -- for a table that already sits inside
   * a card or panel, where a second box would read as a box in a box.
   */
  flush?: boolean;
  /** Current sort. Omit to render plain, non-interactive headers. */
  sort?: SortState;
  /** Called when a sortable header is activated. */
  onSortChange?: (sort: SortState) => void;
}

const alignmentClass: Record<NonNullable<DataTableColumn<unknown>['align']>, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

/**
 * The reusable table for every list screen in the product.
 *
 * It owns all four display states -- loading, error, empty and populated -- so
 * that feature screens never reimplement them and never accidentally render an
 * empty table body while data is still in flight.
 */
export function DataTable<TRow>({
  columns,
  rows,
  getRowId,
  isLoading = false,
  error,
  onRetry,
  onRowClick,
  emptyTitle = 'Nothing to show yet',
  emptyDescription = 'Records will appear here once they exist.',
  emptyAction,
  caption,
  className,
  flush = false,
  sort,
  onSortChange,
}: DataTableProps<TRow>): React.JSX.Element {
  if (error !== undefined && error !== null) {
    return <ErrorState error={error} onRetry={onRetry} compact />;
  }

  if (isLoading) {
    return <TableSkeleton columns={columns.length} />;
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />;
  }

  const isInteractive = typeof onRowClick === 'function';
  const isSortable = sort !== undefined && typeof onSortChange === 'function';

  /** Toggle direction when re-sorting the active column, else start ascending. */
  const nextSortFor = (sortKey: string): SortState =>
    sort !== undefined && sort.sortBy === sortKey
      ? { sortBy: sortKey, sortOrder: sort.sortOrder === 'asc' ? 'desc' : 'asc' }
      : { sortBy: sortKey, sortOrder: 'asc' };

  return (
    <div
      className={cn(
        !flush &&
          'bg-card overflow-hidden rounded-2xl shadow-[0_1px_2px_rgba(20,20,22,0.04),0_0_0_1px_rgba(20,20,22,0.04)]',
        className,
      )}
    >
      <Table>
        {caption ? <caption className="sr-only">{caption}</caption> : null}

        <TableHeader>
          <TableRow className="border-b-0 hover:bg-transparent">
            {columns.map((column) => {
              const sortKey = column.sortKey;
              const canSort = isSortable && sortKey !== undefined;
              const isSorted = canSort && sort.sortBy === sortKey;

              return (
                <TableHead
                  key={column.id}
                  className={cn(alignmentClass[column.align ?? 'left'], column.className)}
                  scope="col"
                  // Announces the current sort to assistive technology, which
                  // an icon alone does not.
                  aria-sort={isSorted ? (sort.sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {canSort ? (
                    <button
                      type="button"
                      onClick={() => {
                        onSortChange(nextSortFor(sortKey));
                      }}
                      className={cn(
                        'hover:text-foreground focus-visible:ring-ring inline-flex items-center gap-1 rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none',
                        isSorted && 'text-foreground',
                      )}
                    >
                      {column.header}
                      {isSorted ? (
                        sort.sortOrder === 'asc' ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    column.header
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>

        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={getRowId(row)}
              className={cn(
                'last:border-b-0',
                isInteractive &&
                  'hover:bg-primary-subtle/60 focus-visible:bg-primary-subtle/60 cursor-pointer focus-visible:outline-none',
              )}
              // Rows become keyboard-operable only when they actually do something.
              {...(isInteractive
                ? {
                    tabIndex: 0,
                    role: 'button',
                    onClick: (event: React.MouseEvent<HTMLTableRowElement>) => {
                      // React routes events from a portal through the component
                      // tree rather than the DOM tree. A row action menu is
                      // rendered from a cell but portalled to the body, so
                      // clicking one of its items arrives here as though the
                      // row itself had been clicked -- and the row would
                      // navigate away, cancelling whatever the menu item just
                      // started.
                      //
                      // The DOM knows better: a click that really happened on
                      // this row has a target inside it.
                      if (!event.currentTarget.contains(event.target as Node)) return;
                      onRowClick(row);
                    },
                    onKeyDown: (event: React.KeyboardEvent<HTMLTableRowElement>) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onRowClick(row);
                      }
                    },
                  }
                : {})}
            >
              {columns.map((column) => (
                <TableCell
                  key={`${getRowId(row)}-${column.id}`}
                  className={cn(
                    alignmentClass[column.align ?? 'left'],
                    column.align === 'right' && 'tabular-nums',
                    column.className,
                  )}
                >
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

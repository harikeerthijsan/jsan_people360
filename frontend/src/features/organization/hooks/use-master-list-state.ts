'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';

import type { SortOrder } from '@/components/common/data-table';
import type { MasterListQuery, RecordStatus } from '@/features/organization/types/organization.types';

/**
 * The four states a list can be filtered to.
 *
 * "Archived" is deliberately part of the same control rather than a separate
 * toggle: a record is either live (active or inactive) or archived, so
 * presenting them as one mutually exclusive choice matches the data.
 */
export type MasterView = 'all' | 'active' | 'inactive' | 'archived';

export const MASTER_VIEW_OPTIONS: { value: MasterView; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'archived', label: 'Archived' },
];

const PAGE_SIZE = 20;

function isMasterView(value: string | null): value is MasterView {
  return value === 'all' || value === 'active' || value === 'inactive' || value === 'archived';
}

export interface MasterListState {
  search: string;
  view: MasterView;
  page: number;
  sortBy: string;
  sortOrder: SortOrder;
  /** Ready to hand to the list API. */
  query: MasterListQuery;
  setSearch: (value: string) => void;
  setView: (value: MasterView) => void;
  setPage: (value: number) => void;
  setSort: (sort: { sortBy: string; sortOrder: SortOrder }) => void;
  reset: () => void;
  isFiltered: boolean;
}

/**
 * List state, stored in the URL.
 *
 * Keeping search, filter, sort and page in the query string means a filtered
 * view can be bookmarked, shared and restored by the back button. Holding it in
 * component state would silently discard all of that on navigation.
 */
export function useMasterListState(defaultSortBy: string): MasterListState {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const search = searchParams.get('q') ?? '';
  const viewParam = searchParams.get('view');
  const view: MasterView = isMasterView(viewParam) ? viewParam : 'all';
  const page = Math.max(1, Number(searchParams.get('page') ?? '1') || 1);
  const sortBy = searchParams.get('sort') ?? defaultSortBy;
  const sortOrder: SortOrder = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

  const commit = React.useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());

      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === '') {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }

      const queryString = next.toString();
      // `replace`, not `push`: typing in the search box should not fill the
      // history stack with one entry per keystroke.
      router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const setSearch = React.useCallback(
    (value: string) => {
      // Any filter change returns to page 1; page 7 of the old result set is
      // rarely a valid page of the new one.
      commit({ q: value, page: null });
    },
    [commit],
  );

  const setView = React.useCallback(
    (value: MasterView) => {
      commit({ view: value === 'all' ? null : value, page: null });
    },
    [commit],
  );

  const setPage = React.useCallback(
    (value: number) => {
      commit({ page: value <= 1 ? null : String(value) });
    },
    [commit],
  );

  const setSort = React.useCallback(
    (sort: { sortBy: string; sortOrder: SortOrder }) => {
      commit({
        sort: sort.sortBy === defaultSortBy && sort.sortOrder === 'asc' ? null : sort.sortBy,
        dir: sort.sortOrder === 'asc' ? null : 'desc',
        page: null,
      });
    },
    [commit, defaultSortBy],
  );

  const reset = React.useCallback(() => {
    router.replace(pathname, { scroll: false });
  }, [pathname, router]);

  const query = React.useMemo<MasterListQuery>(() => {
    const status: RecordStatus | undefined =
      view === 'active' ? 'active' : view === 'inactive' ? 'inactive' : undefined;

    return {
      page,
      page_size: PAGE_SIZE,
      ...(search ? { search } : {}),
      ...(status ? { status } : {}),
      archived: view === 'archived',
      sort_by: sortBy,
      sort_order: sortOrder,
    };
  }, [page, search, sortBy, sortOrder, view]);

  return {
    search,
    view,
    page,
    sortBy,
    sortOrder,
    query,
    setSearch,
    setView,
    setPage,
    setSort,
    reset,
    isFiltered: search !== '' || view !== 'all',
  };
}

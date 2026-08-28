'use client';

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import * as React from 'react';

import { toast } from '@/components/ui/sonner';
import { createMasterApi } from '@/features/organization/api/organization.api';
import type {
  MasterFormValues,
  MasterListQuery,
  MasterRecord,
  MasterSlug,
} from '@/features/organization/types/organization.types';
import type { Page } from '@/lib/api/types';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/**
 * Data hooks for the master-data screens.
 *
 * All nine masters share these, so cache invalidation, toast copy and error
 * handling behave identically everywhere instead of being re-implemented per
 * entity with slightly different bugs.
 */

/** Memoised API client for a slug. */
function useMasterApi(slug: MasterSlug) {
  return React.useMemo(() => createMasterApi(slug), [slug]);
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------
export function useMasterList(
  slug: MasterSlug,
  query: MasterListQuery,
): UseQueryResult<Page<MasterRecord>, AppError> {
  const masterApi = useMasterApi(slug);

  return useQuery<Page<MasterRecord>, AppError>({
    queryKey: queryKeys.masters.list(slug, query),
    queryFn: () => masterApi.list(query),
    // Keeps the previous page on screen while the next one loads, so paging
    // and typing in the search box do not blank the table.
    placeholderData: (previous) => previous,
  });
}

export function useMasterRecord(
  slug: MasterSlug,
  id: string | undefined,
): UseQueryResult<MasterRecord, AppError> {
  const masterApi = useMasterApi(slug);

  return useQuery<MasterRecord, AppError>({
    queryKey: queryKeys.masters.detail(slug, id ?? ''),
    queryFn: () => masterApi.get(id ?? ''),
    enabled: Boolean(id),
  });
}

/**
 * Active records of a master, for populating a reference picker.
 *
 * Only live, active records are offered: the API refuses to attach a child to
 * an archived or inactive parent, so listing them would invite a 409.
 */
export function useMasterOptions(slug: MasterSlug | undefined): UseQueryResult<Page<MasterRecord>, AppError> {
  const masterApi = useMasterApi(slug ?? 'business-units');

  return useQuery<Page<MasterRecord>, AppError>({
    queryKey: queryKeys.masters.options(slug ?? ''),
    queryFn: () =>
      masterApi.list({
        page: 1,
        page_size: 100,
        status: 'active',
        archived: false,
        sort_by: 'name',
        sort_order: 'asc',
      }),
    enabled: Boolean(slug),
    staleTime: 5 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
interface UpdateArgs {
  id: string;
  values: MasterFormValues;
}

export function useCreateMaster(
  slug: MasterSlug,
  entityLabel: string,
): UseMutationResult<MasterRecord, AppError, MasterFormValues> {
  const masterApi = useMasterApi(slug);
  const queryClient = useQueryClient();

  return useMutation<MasterRecord, AppError, MasterFormValues>({
    mutationFn: (values) => masterApi.create(values),
    onSuccess: (record) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.masters.all(slug) });
      toast.success(`${entityLabel} created`, { description: record.name });
    },
  });
}

export function useUpdateMaster(
  slug: MasterSlug,
  entityLabel: string,
): UseMutationResult<MasterRecord, AppError, UpdateArgs> {
  const masterApi = useMasterApi(slug);
  const queryClient = useQueryClient();

  return useMutation<MasterRecord, AppError, UpdateArgs>({
    mutationFn: ({ id, values }) => masterApi.update(id, values),
    onSuccess: (record) => {
      queryClient.setQueryData(queryKeys.masters.detail(slug, record.id), record);
      void queryClient.invalidateQueries({ queryKey: queryKeys.masters.all(slug) });
      toast.success(`${entityLabel} updated`, { description: record.name });
    },
  });
}

export function useArchiveMaster(
  slug: MasterSlug,
  entityLabel: string,
): UseMutationResult<MasterRecord, AppError, string> {
  const masterApi = useMasterApi(slug);
  const queryClient = useQueryClient();

  return useMutation<MasterRecord, AppError, string>({
    mutationFn: (id) => masterApi.archive(id),
    onSuccess: (record) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.masters.all(slug) });
      toast.success(`${entityLabel} archived`, { description: record.name });
    },
    onError: (error) => {
      // Archiving is refused when live children still reference the record.
      // The API explains why, so surface that rather than a generic failure.
      toast.error(`Could not archive this ${entityLabel.toLowerCase()}`, {
        description: error.message,
      });
    },
  });
}

export function useRestoreMaster(
  slug: MasterSlug,
  entityLabel: string,
): UseMutationResult<MasterRecord, AppError, string> {
  const masterApi = useMasterApi(slug);
  const queryClient = useQueryClient();

  return useMutation<MasterRecord, AppError, string>({
    mutationFn: (id) => masterApi.restore(id),
    onSuccess: (record) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.masters.all(slug) });
      toast.success(`${entityLabel} restored`, { description: record.name });
    },
    onError: (error) => {
      toast.error(`Could not restore this ${entityLabel.toLowerCase()}`, {
        description: error.message,
      });
    },
  });
}

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
import { documentsApi, type UploadFields } from '@/features/documents/api/documents.api';
import type {
  DocumentCategoryRecord,
  DocumentAuditEntry,
  DocumentDashboardStats,
  DocumentListQuery,
  DocumentRecord,
  DocumentTypeRecord,
  DocumentVersionRecord,
} from '@/features/documents/types/document.types';
import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/**
 * Data hooks for the document screens.
 *
 * Uploads are their own shape: they report progress, so the percentage lives in
 * component state alongside the mutation rather than inside it.
 */

export function useDocumentList(query: DocumentListQuery): UseQueryResult<Page<DocumentRecord>, AppError> {
  return useQuery<Page<DocumentRecord>, AppError>({
    queryKey: queryKeys.documents.list(query),
    queryFn: () => documentsApi.list(query),
    placeholderData: (previous) => previous,
  });
}

export function useDocument(id: string | undefined): UseQueryResult<DocumentRecord, AppError> {
  return useQuery<DocumentRecord, AppError>({
    queryKey: queryKeys.documents.detail(id ?? ''),
    queryFn: () => documentsApi.get(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useDocumentVersions(
  id: string | undefined,
): UseQueryResult<DocumentVersionRecord[], AppError> {
  return useQuery<DocumentVersionRecord[], AppError>({
    queryKey: queryKeys.documents.versions(id ?? ''),
    queryFn: () => documentsApi.versions(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useDocumentAudit(id: string | undefined): UseQueryResult<DocumentAuditEntry[], AppError> {
  return useQuery<DocumentAuditEntry[], AppError>({
    queryKey: queryKeys.documents.audit(id ?? ''),
    queryFn: () => documentsApi.audit(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useDocumentDashboard(): UseQueryResult<DocumentDashboardStats, AppError> {
  return useQuery<DocumentDashboardStats, AppError>({
    queryKey: queryKeys.documents.dashboard(),
    queryFn: () => documentsApi.dashboard(),
  });
}

/**
 * The categories and types available to choose from.
 *
 * Only the active, live ones: a picker offering an archived category would let
 * someone select something the server then refuses.
 */
export function useDocumentCategories(): UseQueryResult<Page<DocumentCategoryRecord>, AppError> {
  return useQuery<Page<DocumentCategoryRecord>, AppError>({
    queryKey: queryKeys.documents.categories(),
    queryFn: () =>
      api.get<Page<DocumentCategoryRecord>>(endpoints.documents.categories, {
        params: { page_size: '100', status: 'active', sort_by: 'display_order', sort_order: 'asc' },
      }),
    staleTime: 5 * 60_000,
  });
}

export function useDocumentTypes(categoryId?: string): UseQueryResult<Page<DocumentTypeRecord>, AppError> {
  return useQuery<Page<DocumentTypeRecord>, AppError>({
    queryKey: queryKeys.documents.types(categoryId),
    queryFn: () =>
      api.get<Page<DocumentTypeRecord>>(endpoints.documents.types, {
        params: {
          page_size: '100',
          status: 'active',
          sort_by: 'name',
          sort_order: 'asc',
          ...(categoryId ? { category_id: categoryId } : {}),
        },
      }),
    staleTime: 5 * 60_000,
  });
}

/**
 * Every category or type, for the administration screen.
 *
 * Separate from the picker hooks above, which deliberately fetch only what may
 * be *chosen*. An administrator has to see the inactive ones to reactivate them
 * and the archived ones to restore them — filtering those out is right for a
 * form and wrong for the screen that manages them.
 */
export function useDocumentMasters(
  kind: 'categories' | 'types',
  archived: boolean,
): UseQueryResult<Page<DocumentCategoryRecord & Partial<DocumentTypeRecord>>, AppError> {
  return useQuery<Page<DocumentCategoryRecord & Partial<DocumentTypeRecord>>, AppError>({
    queryKey: [...queryKeys.documents.root, 'admin', kind, archived],
    queryFn: () =>
      api.get<Page<DocumentCategoryRecord & Partial<DocumentTypeRecord>>>(endpoints.documents[kind], {
        params: {
          page_size: '100',
          archived: String(archived),
          sort_by: kind === 'categories' ? 'display_order' : 'name',
          sort_order: 'asc',
        },
      }),
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
function useDocumentMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<DocumentRecord>,
  labels: { done: string; failed: string },
): UseMutationResult<DocumentRecord, AppError, TVariables> {
  const queryClient = useQueryClient();

  return useMutation<DocumentRecord, AppError, TVariables>({
    mutationFn,
    onSuccess: (document) => {
      queryClient.setQueryData(queryKeys.documents.detail(document.id), document);
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.root });
      toast.success(labels.done, { description: `${document.name} · ${document.document_code}` });
    },
    onError: (error) => {
      // The server's message verbatim: an upload is refused for specific,
      // actionable reasons — the wrong file type, a duplicate, a missing expiry
      // date — and a generic failure would hide the part that matters.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export interface UploadArgs {
  file: File;
  fields: UploadFields;
}

/**
 * Upload a new document, reporting progress.
 *
 * The percentage is component state rather than mutation state because axios
 * reports it through a callback, and threading it through TanStack Query would
 * mean a re-render of the whole mutation on every chunk.
 */
export function useUploadDocument(): UseMutationResult<DocumentRecord, AppError, UploadArgs> & {
  progress: number;
} {
  const [progress, setProgress] = React.useState(0);

  const mutation = useDocumentMutation<UploadArgs>(
    ({ file, fields }) => documentsApi.upload(file, fields, setProgress),
    { done: 'Document uploaded', failed: 'Could not upload this document' },
  );

  // Reset between attempts, so a retry after a failure does not start at 100%.
  React.useEffect(() => {
    if (mutation.isPending) setProgress(0);
  }, [mutation.isPending]);

  return { ...mutation, progress };
}

export interface NewVersionArgs {
  file: File;
  notes: string | null;
}

export function useUploadVersion(
  id: string,
): UseMutationResult<DocumentRecord, AppError, NewVersionArgs> & { progress: number } {
  const [progress, setProgress] = React.useState(0);

  const mutation = useDocumentMutation<NewVersionArgs>(
    ({ file, notes }) => documentsApi.uploadVersion(id, file, notes, setProgress),
    { done: 'New version uploaded', failed: 'Could not upload this version' },
  );

  React.useEffect(() => {
    if (mutation.isPending) setProgress(0);
  }, [mutation.isPending]);

  return { ...mutation, progress };
}

export function useUpdateDocument(id: string): UseMutationResult<DocumentRecord, AppError, unknown> {
  return useDocumentMutation((values: unknown) => documentsApi.update(id, values), {
    done: 'Document updated',
    failed: 'Could not update this document',
  });
}

export function useReviewDocument(id: string): UseMutationResult<DocumentRecord, AppError, unknown> {
  return useDocumentMutation((values: unknown) => documentsApi.review(id, values), {
    done: 'Review recorded',
    failed: 'Could not record the review',
  });
}

export type DocumentAction = 'archive' | 'restore';

const ACTION_LABELS: Record<DocumentAction, { done: string; failed: string }> = {
  archive: { done: 'Document archived', failed: 'Could not archive this document' },
  restore: { done: 'Document restored', failed: 'Could not restore this document' },
};

export function useDocumentAction(
  action: DocumentAction,
): UseMutationResult<DocumentRecord, AppError, string> {
  return useDocumentMutation((id: string) => documentsApi[action](id), ACTION_LABELS[action]);
}

/**
 * Download a version, saving it under its original filename.
 *
 * A mutation rather than a query: it has a side effect, it is triggered by a
 * click, and every call is recorded in the audit trail — none of which suits
 * something that might be cached or refetched.
 */
export function useDownloadDocument(): UseMutationResult<
  void,
  AppError,
  { id: string; filename: string; versionId?: string }
> {
  return useMutation<void, AppError, { id: string; filename: string; versionId?: string }>({
    mutationFn: ({ id, filename, versionId }) => documentsApi.download(id, filename, versionId),
    onError: (error) => {
      toast.error('Could not download this document', { description: error.message });
    },
  });
}

/**
 * Fetch a preview as an object URL, and revoke it on unmount.
 *
 * The endpoint requires a bearer token, so the bytes have to be fetched by the
 * app rather than by pointing an `<img>` at the URL. Revoking matters: an
 * object URL holds the blob in memory until it is released.
 */
export function useDocumentPreview(
  id: string | undefined,
  versionId: string | undefined,
  enabled: boolean,
): { url: string | null; isLoading: boolean; error: AppError | null } {
  const [url, setUrl] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState<AppError | null>(null);

  React.useEffect(() => {
    if (!id || !enabled) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    documentsApi
      .previewUrl(id, versionId)
      .then((created) => {
        objectUrl = created;
        // The dialog may have closed while the bytes were in flight.
        if (cancelled) {
          URL.revokeObjectURL(created);
          return;
        }
        setUrl(created);
      })
      .catch((caught: AppError) => {
        if (!cancelled) setError(caught);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [id, versionId, enabled]);

  return { url, isLoading, error };
}

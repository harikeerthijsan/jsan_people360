import { QueryClient } from '@tanstack/react-query';

import { AppError } from '@/lib/errors';

/**
 * Build a QueryClient with the platform's caching and retry policy.
 *
 * A factory rather than a module singleton: in the App Router a singleton would
 * be shared across users during server rendering, leaking one user's cached data
 * into another's response.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Data stays fresh for a minute; a tab switch will not stampede the API.
        staleTime: 60_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying a 4xx just repeats a request the server already refused.
          if (error instanceof AppError) {
            if (error.status !== null && error.status >= 400 && error.status < 500) {
              return false;
            }
          }
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: {
        // Mutations are not idempotent -- never retry them automatically.
        retry: false,
      },
    },
  });
}

/**
 * Centralised query keys.
 *
 * Declaring them in one place keeps invalidation honest: a feature can
 * invalidate `queryKeys.auth.currentUser()` without guessing the array shape
 * another module used.
 */
export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    currentUser: () => [...queryKeys.auth.all, 'current-user'] as const,
  },
  health: {
    all: ['health'] as const,
    readiness: () => [...queryKeys.health.all, 'readiness'] as const,
  },
  /**
   * Master-data keys are nested under the master's slug so that invalidating
   * `masters.all(slug)` clears that master's lists and details together, and
   * nothing else.
   */
  masters: {
    root: ['masters'] as const,
    all: (slug: string) => [...queryKeys.masters.root, slug] as const,
    // The query object is part of the key, so a different filter set is a
    // different cache entry. It is accepted as `unknown` because each master's
    // query shape differs and the key only needs it to be serialisable.
    list: (slug: string, query: unknown) => [...queryKeys.masters.all(slug), 'list', query] as const,
    detail: (slug: string, id: string) => [...queryKeys.masters.all(slug), 'detail', id] as const,
    options: (slug: string) => [...queryKeys.masters.all(slug), 'options'] as const,
    primaryOrganization: () => [...queryKeys.masters.root, 'primary-organization'] as const,
  },
  users: {
    root: ['users'] as const,
    list: (query: unknown) => [...queryKeys.users.root, 'list', query] as const,
    detail: (id: string) => [...queryKeys.users.root, 'detail', id] as const,
  },
  employees: {
    root: ['employees'] as const,
    list: (query: unknown) => [...queryKeys.employees.root, 'list', query] as const,
    detail: (id: string) => [...queryKeys.employees.root, 'detail', id] as const,
    history: (id: string) => [...queryKeys.employees.root, 'history', id] as const,
    audit: (id: string) => [...queryKeys.employees.root, 'audit', id] as const,
    dashboard: () => [...queryKeys.employees.root, 'dashboard'] as const,
    // Deliberately *not* nested under `detail`, so invalidating an employee
    // does not refetch their unmasked details -- every fetch of those is
    // audited, and an invalidation is not a decision to look.
    sensitive: (id: string) => [...queryKeys.employees.root, 'sensitive', id] as const,
  },
  documents: {
    root: ['documents'] as const,
    list: (query: unknown) => [...queryKeys.documents.root, 'list', query] as const,
    detail: (id: string) => [...queryKeys.documents.root, 'detail', id] as const,
    versions: (id: string) => [...queryKeys.documents.root, 'versions', id] as const,
    audit: (id: string) => [...queryKeys.documents.root, 'audit', id] as const,
    dashboard: () => [...queryKeys.documents.root, 'dashboard'] as const,
    // Nested under the document so archiving one clears its own list entries
    // without disturbing anything else.
    categories: () => [...queryKeys.documents.root, 'categories'] as const,
    types: (categoryId?: string) => [...queryKeys.documents.root, 'types', categoryId ?? 'all'] as const,
  },
  requisitions: {
    root: ['requisitions'] as const,
    list: (query: unknown) => [...queryKeys.requisitions.root, 'list', query] as const,
    detail: (id: string) => [...queryKeys.requisitions.root, 'detail', id] as const,
    dashboard: () => [...queryKeys.requisitions.root, 'dashboard'] as const,
  },
} as const;

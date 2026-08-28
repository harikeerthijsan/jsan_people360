'use client';

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import { employeesApi } from '@/features/employees/api/employees.api';
import type {
  EmployeeAuditEntry,
  EmployeeDashboardStats,
  EmployeeListQuery,
  EmployeeRecord,
  EmployeeSensitiveReveal,
  EmploymentHistoryEntry,
  ExportFormat,
} from '@/features/employees/types/employee.types';
import type { Page } from '@/lib/api/types';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/**
 * Data hooks for the employee screens.
 *
 * The lifecycle actions share one mutation factory so that cache invalidation
 * and the failure toast behave identically for all of them, rather than being
 * re-implemented per action with slightly different bugs.
 */

export function useEmployeeList(query: EmployeeListQuery): UseQueryResult<Page<EmployeeRecord>, AppError> {
  return useQuery<Page<EmployeeRecord>, AppError>({
    queryKey: queryKeys.employees.list(query),
    queryFn: () => employeesApi.list(query),
    // Keeps the previous page on screen while the next loads, so paging and
    // typing in the search box do not blank the table.
    placeholderData: (previous) => previous,
  });
}

export function useEmployee(id: string | undefined): UseQueryResult<EmployeeRecord, AppError> {
  return useQuery<EmployeeRecord, AppError>({
    queryKey: queryKeys.employees.detail(id ?? ''),
    queryFn: () => employeesApi.get(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useEmploymentHistory(
  id: string | undefined,
  enabled = true,
): UseQueryResult<EmploymentHistoryEntry[], AppError> {
  return useQuery<EmploymentHistoryEntry[], AppError>({
    queryKey: queryKeys.employees.history(id ?? ''),
    queryFn: () => employeesApi.history(id ?? ''),
    enabled: Boolean(id) && enabled,
  });
}

export function useEmployeeAudit(id: string | undefined): UseQueryResult<EmployeeAuditEntry[], AppError> {
  return useQuery<EmployeeAuditEntry[], AppError>({
    queryKey: queryKeys.employees.audit(id ?? ''),
    queryFn: () => employeesApi.audit(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useEmployeeDashboard(): UseQueryResult<EmployeeDashboardStats, AppError> {
  return useQuery<EmployeeDashboardStats, AppError>({
    queryKey: queryKeys.employees.dashboard(),
    queryFn: () => employeesApi.dashboard(),
  });
}

/**
 * Fetch the unmasked bank and identity details.
 *
 * `enabled` defaults to false and `staleTime: 0` is deliberate: every call is
 * written to the audit trail, so the request must happen only when someone has
 * actually asked to see the values, and must not be served from a cache that
 * outlives that decision.
 */
export function useEmployeeSensitive(
  id: string | undefined,
  enabled: boolean,
): UseQueryResult<EmployeeSensitiveReveal, AppError> {
  return useQuery<EmployeeSensitiveReveal, AppError>({
    queryKey: queryKeys.employees.sensitive(id ?? ''),
    queryFn: () => employeesApi.sensitive(id ?? ''),
    enabled: Boolean(id) && enabled,
    staleTime: 0,
    gcTime: 0,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
function useEmployeeMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<EmployeeRecord>,
  labels: { done: string; failed: string },
): UseMutationResult<EmployeeRecord, AppError, TVariables> {
  const queryClient = useQueryClient();

  return useMutation<EmployeeRecord, AppError, TVariables>({
    mutationFn,
    onSuccess: (employee) => {
      queryClient.setQueryData(queryKeys.employees.detail(employee.id), employee);
      void queryClient.invalidateQueries({ queryKey: queryKeys.employees.root });
      toast.success(labels.done, { description: `${employee.full_name} · ${employee.employee_code}` });
    },
    onError: (error) => {
      // The server's message verbatim: these actions are refused for specific,
      // actionable reasons -- a reporting loop, a manager with reports -- and a
      // generic "something went wrong" would hide exactly the part that matters.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export function useCreateEmployee(): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi.create(values), {
    done: 'Employee created',
    failed: 'Could not create this employee',
  });
}

export function useUpdateEmployee(id: string): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi.update(id, values), {
    done: 'Employee updated',
    failed: 'Could not update this employee',
  });
}

export function useSetBankDetail(id: string): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi.setBankDetail(id, values), {
    done: 'Bank details updated',
    failed: 'Could not update the bank details',
  });
}

export function useSetIdentification(id: string): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi.setIdentification(id, values), {
    done: 'Government identifiers updated',
    failed: 'Could not update the identifiers',
  });
}

export function useSetAddress(id: string): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi.setAddress(id, values), {
    done: 'Address updated',
    failed: 'Could not update the address',
  });
}

/** The lifecycle actions that take a payload. */
export type LifecycleAction =
  | 'confirm'
  | 'transfer'
  | 'changeDesignation'
  | 'changeManager'
  | 'changeLocation'
  | 'promote'
  | 'changeStatus';

const LIFECYCLE_LABELS: Record<LifecycleAction, { done: string; failed: string }> = {
  confirm: { done: 'Employee confirmed', failed: 'Could not confirm this employee' },
  transfer: { done: 'Employee transferred', failed: 'Could not transfer this employee' },
  changeDesignation: { done: 'Designation changed', failed: 'Could not change the designation' },
  changeManager: { done: 'Reporting manager changed', failed: 'Could not change the manager' },
  changeLocation: { done: 'Work location changed', failed: 'Could not change the location' },
  promote: { done: 'Employee promoted', failed: 'Could not record the promotion' },
  changeStatus: { done: 'Status changed', failed: 'Could not change the status' },
};

export function useLifecycleAction(
  action: LifecycleAction,
  id: string,
): UseMutationResult<EmployeeRecord, AppError, unknown> {
  return useEmployeeMutation((values: unknown) => employeesApi[action](id, values), LIFECYCLE_LABELS[action]);
}

/** The lifecycle actions that take no payload. */
export type SimpleAction = 'activate' | 'deactivate' | 'archive' | 'restore';

const SIMPLE_LABELS: Record<SimpleAction, { done: string; failed: string }> = {
  activate: { done: 'Employee activated', failed: 'Could not activate this employee' },
  deactivate: { done: 'Employee deactivated', failed: 'Could not deactivate this employee' },
  archive: { done: 'Employee archived', failed: 'Could not archive this employee' },
  restore: { done: 'Employee restored', failed: 'Could not restore this employee' },
};

export function useSimpleAction(action: SimpleAction): UseMutationResult<EmployeeRecord, AppError, string> {
  return useEmployeeMutation((id: string) => employeesApi[action](id), SIMPLE_LABELS[action]);
}

/**
 * Download the directory as a file.
 *
 * The blob is turned into a click on a temporary anchor: that is the only way
 * to make the browser save a response the page fetched itself, and it keeps the
 * request authenticated, which a plain link to the endpoint would not be.
 */
export function useExportEmployees(): UseMutationResult<
  void,
  AppError,
  { query: EmployeeListQuery; format: ExportFormat }
> {
  return useMutation<void, AppError, { query: EmployeeListQuery; format: ExportFormat }>({
    mutationFn: async ({ query, format }) => {
      const { blob, filename } = await employeesApi.export(query, format);

      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
    onSuccess: () => {
      toast.success('Export ready', { description: 'Your download should have started.' });
    },
    onError: (error) => {
      toast.error('Could not export the directory', { description: error.message });
    },
  });
}

'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { assetApi } from './api';
import type {
  Asset,
  AssetCreateInput,
  AssetFilters,
  AssetUpdateInput,
  AssignInput,
  MaintenanceCreateInput,
  MaintenanceUpdateInput,
  ReturnInput,
  StatusChangeInput,
  TransferInput,
} from './types';

/**
 * Data hooks for the asset screens.
 *
 * Four query roots, matching the four audiences: an employee's own list must
 * not be evicted every time an administrator ticks a maintenance record, and an
 * HR clearance view must not be evicted by an employee opening their page.
 *
 * Within the admin root, a custody mutation invalidates the whole root. The
 * figures interlock -- assigning a laptop changes the register, the dashboard
 * counters, the asset's own detail and its history at once -- and invalidating
 * selectively is how two numbers on the same screen end up disagreeing.
 */

const mineKey = ['me', 'assets'] as const;
const teamKey = ['manager', 'assets'] as const;
const hrKey = ['hr', 'assets'] as const;
const adminKey = ['assets'] as const;

// ---------------------------------------------------------------------------
// Employee, manager, HR
// ---------------------------------------------------------------------------
export const useMyAssets = () => useQuery({ queryKey: mineKey, queryFn: () => assetApi.mine.list() });

export const useTeamAssets = () => useQuery({ queryKey: teamKey, queryFn: () => assetApi.team.list() });

export const useEmployeeAssets = (employeeId: string) =>
  useQuery({
    queryKey: [...hrKey, employeeId],
    queryFn: () => assetApi.hr.forEmployee(employeeId),
    enabled: Boolean(employeeId),
  });

// ---------------------------------------------------------------------------
// Admin: reads
// ---------------------------------------------------------------------------
export const useAssets = (filters: AssetFilters = {}) =>
  useQuery({
    queryKey: [...adminKey, 'list', filters],
    queryFn: () => assetApi.admin.list(filters),
    // The register is filtered server-side, so a new filter is a new query
    // rather than a re-filter of something already in memory.
    placeholderData: (previous) => previous,
  });

export const useAsset = (assetId: string) =>
  useQuery({
    queryKey: [...adminKey, 'detail', assetId],
    queryFn: () => assetApi.admin.get(assetId),
    enabled: Boolean(assetId),
  });

export const useAssetCategories = (includeInactive = false) =>
  useQuery({
    queryKey: [...adminKey, 'categories', includeInactive],
    queryFn: () => assetApi.admin.categories(includeInactive),
    // Master data: changes rarely, read on nearly every asset screen.
    staleTime: 5 * 60_000,
  });

export const useAssetDashboard = () =>
  useQuery({
    queryKey: [...adminKey, 'dashboard'],
    queryFn: () => assetApi.admin.dashboard(),
    staleTime: 30_000,
  });

export const useMaintenanceRecords = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'maintenance', params],
    queryFn: () => assetApi.admin.maintenance(params),
  });

// ---------------------------------------------------------------------------
// Admin: writes
// ---------------------------------------------------------------------------
const useAssetMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: adminKey });
      // A custody change is also visible on the employee's own page and on
      // their manager's, so those roots are refreshed too.
      void queryClient.invalidateQueries({ queryKey: mineKey });
      void queryClient.invalidateQueries({ queryKey: teamKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useCreateAsset = (): UseMutationResult<Asset, AppError, AssetCreateInput> =>
  useAssetMutation((input) => assetApi.admin.create(input), 'Asset registered');

export const useUpdateAsset = () =>
  useAssetMutation(
    ({ assetId, payload }: { assetId: string; payload: AssetUpdateInput }) =>
      assetApi.admin.update(assetId, payload),
    'Asset updated',
  );

export const useAssignAsset = () =>
  useAssetMutation(
    ({ assetId, payload }: { assetId: string; payload: AssignInput }) =>
      assetApi.admin.assign(assetId, payload),
    'Asset assigned',
  );

export const useReturnAsset = () =>
  useAssetMutation(
    ({ assetId, payload }: { assetId: string; payload: ReturnInput }) =>
      assetApi.admin.processReturn(assetId, payload),
    'Return recorded',
  );

export const useTransferAsset = () =>
  useAssetMutation(
    ({ assetId, payload }: { assetId: string; payload: TransferInput }) =>
      assetApi.admin.transfer(assetId, payload),
    'Asset transferred',
  );

export const useChangeAssetStatus = () =>
  useAssetMutation(
    ({ assetId, payload }: { assetId: string; payload: StatusChangeInput }) =>
      assetApi.admin.changeStatus(assetId, payload),
    'Status updated',
  );

export const useScheduleMaintenance = () =>
  useAssetMutation(
    (payload: MaintenanceCreateInput) => assetApi.admin.scheduleMaintenance(payload),
    'Maintenance recorded',
  );

export const useUpdateMaintenance = () =>
  useAssetMutation(
    ({ maintenanceId, payload }: { maintenanceId: string; payload: MaintenanceUpdateInput }) =>
      assetApi.admin.updateMaintenance(maintenanceId, payload),
    'Maintenance updated',
  );

export const useCreateAssetCategory = () =>
  useAssetMutation(
    (payload: { name: string; code: string; returnable?: boolean }) => assetApi.admin.createCategory(payload),
    'Category created',
  );

export const useUpdateAssetCategory = () =>
  useAssetMutation(
    ({
      categoryId,
      payload,
    }: {
      categoryId: string;
      payload: { name?: string; returnable?: boolean; status?: 'active' | 'inactive' };
    }) => assetApi.admin.updateCategory(categoryId, payload),
    'Category updated',
  );

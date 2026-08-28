import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  Asset,
  AssetAssignment,
  AssetCategory,
  AssetDashboard,
  AssetDetail,
  AssetCreateInput,
  AssetFilters,
  AssetReportId,
  AssetStatus,
  AssetUpdateInput,
  AssignInput,
  EmployeeAssetClearanceRow,
  Maintenance,
  MaintenanceCreateInput,
  MaintenanceUpdateInput,
  MyAsset,
  ReturnInput,
  StatusChangeInput,
  TeamAssetRow,
  TransferInput,
} from './types';

/**
 * Transport for the four asset audiences.
 *
 * Split into `mine`, `team`, `hr` and `admin` because the server splits them
 * the same way, and the split is the access model rather than a naming
 * convention. Nothing under `mine` carries an employee id -- there is nowhere
 * to put one -- and the ids the others pass are checked against the caller's
 * scope by the server before anything is read.
 *
 * Every list call goes to the server with its filters. Nothing here fetches the
 * register and filters it in the browser: §5 of the brief is explicit, and a
 * client-side filter over a paginated response would be wrong as well as slow.
 */

const me = endpoints.me.root;
const manager = endpoints.manager.root;
const hr = endpoints.hr.root;
const root = endpoints.assets.root;

export const assetApi = {
  /** The signed-in employee's own assets. */
  mine: {
    list: () => api.get<MyAsset[]>(`${me}/assets`),
  },

  /** A manager's direct reports, and nobody else's. */
  team: {
    list: () => api.get<TeamAssetRow[]>(`${manager}/assets`),
  },

  /** HR: sight of what one employee holds, for a clearance. Read only. */
  hr: {
    forEmployee: (employeeId: string) => api.get<EmployeeAssetClearanceRow[]>(`${hr}/assets/${employeeId}`),
  },

  /** Administrators. Each call is permission-guarded on the server. */
  admin: {
    list: (filters: AssetFilters = {}) =>
      api.get<Page<Asset>>(root, { params: { page: 1, page_size: 20, ...filters } }),
    get: (assetId: string) => api.get<AssetDetail>(`${root}/${assetId}`),
    create: (payload: AssetCreateInput) => api.post<Asset>(root, payload),
    update: (assetId: string, payload: AssetUpdateInput) => api.patch<Asset>(`${root}/${assetId}`, payload),

    assign: (assetId: string, payload: AssignInput) =>
      api.post<AssetAssignment>(`${root}/${assetId}/assign`, payload),
    processReturn: (assetId: string, payload: ReturnInput) =>
      api.post<unknown>(`${root}/${assetId}/return`, payload),
    transfer: (assetId: string, payload: TransferInput) =>
      api.post<unknown>(`${root}/${assetId}/transfer`, payload),
    changeStatus: (assetId: string, payload: StatusChangeInput) =>
      api.post<Asset>(`${root}/${assetId}/status`, payload),
    transitions: (assetId: string) => api.get<AssetStatus[]>(`${root}/${assetId}/transitions`),

    categories: (includeInactive = false) =>
      api.get<AssetCategory[]>(`${root}/categories`, {
        params: { include_inactive: includeInactive },
      }),
    createCategory: (payload: { name: string; code: string; returnable?: boolean }) =>
      api.post<AssetCategory>(`${root}/categories`, payload),
    updateCategory: (
      categoryId: string,
      payload: { name?: string; returnable?: boolean; status?: 'active' | 'inactive' },
    ) => api.patch<AssetCategory>(`${root}/categories/${categoryId}`, payload),

    dashboard: () => api.get<AssetDashboard>(`${root}/dashboard`),

    maintenance: (params: Record<string, unknown> = {}) =>
      api.get<Page<Maintenance>>(`${root}/maintenance`, {
        params: { page: 1, page_size: 20, ...params },
      }),
    scheduleMaintenance: (payload: MaintenanceCreateInput) =>
      api.post<Maintenance>(`${root}/maintenance`, payload),
    updateMaintenance: (maintenanceId: string, payload: MaintenanceUpdateInput) =>
      api.patch<Maintenance>(`${root}/maintenance/${maintenanceId}`, payload),

    /** The export URL. Downloaded through the browser so the server sets the filename. */
    reportUrl: (report: AssetReportId, fmt: 'csv' | 'xlsx') => `${root}/reports/${report}/export?fmt=${fmt}`,
  },
};

import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type {
  EmployeeAuditEntry,
  EmployeeDashboardStats,
  EmployeeListQuery,
  EmployeeRecord,
  EmployeeSensitiveReveal,
  EmploymentHistoryEntry,
  ExportFormat,
} from '@/features/employees/types/employee.types';

/** Transport for the Employee Management endpoints. */

const root = endpoints.employees.root;

/**
 * Only the parameters that carry a value are sent.
 *
 * An empty string reaches the server as a real value and fails validation,
 * where an absent parameter correctly means "no filter".
 */
function toQueryParams(query: EmployeeListQuery): Record<string, string> {
  const params: Record<string, string> = {
    page: String(query.page),
    page_size: String(query.page_size),
    sort_by: query.sort_by,
    sort_order: query.sort_order,
    archived: String(query.archived),
  };

  const optional: (keyof EmployeeListQuery)[] = [
    'search',
    'employment_status',
    'business_unit_id',
    'team_id',
    'designation_id',
    'grade_id',
    'work_location_id',
    'employment_type_id',
    'reporting_manager_id',
    'work_mode',
    'joined_from',
    'joined_to',
  ];

  for (const key of optional) {
    const value = query[key];
    if (typeof value === 'string' && value !== '') {
      params[key] = value;
    }
  }

  return params;
}

export interface ExportResult {
  blob: Blob;
  filename: string;
}

/** Pull the filename the server chose out of the Content-Disposition header. */
function filenameFrom(header: string | undefined, fallback: string): string {
  const match = header ? /filename="?([^"]+)"?/.exec(header) : null;
  return match?.[1] ?? fallback;
}

export const employeesApi = {
  list: (query: EmployeeListQuery): Promise<Page<EmployeeRecord>> =>
    api.get<Page<EmployeeRecord>>(root, { params: toQueryParams(query) }),

  get: (id: string): Promise<EmployeeRecord> => api.get<EmployeeRecord>(`${root}/${id}`),

  create: (values: unknown): Promise<EmployeeRecord> => api.post<EmployeeRecord>(root, values),

  update: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.patch<EmployeeRecord>(`${root}/${id}`, values),

  history: (id: string): Promise<EmploymentHistoryEntry[]> =>
    api.get<EmploymentHistoryEntry[]>(`${root}/${id}/history`),

  audit: (id: string): Promise<EmployeeAuditEntry[]> => api.get<EmployeeAuditEntry[]>(`${root}/${id}/audit`),

  dashboard: (): Promise<EmployeeDashboardStats> =>
    api.get<EmployeeDashboardStats>(endpoints.employees.dashboard),

  /** Audited on the server. Never call this to "warm" a cache. */
  sensitive: (id: string): Promise<EmployeeSensitiveReveal> =>
    api.get<EmployeeSensitiveReveal>(`${root}/${id}/sensitive`),

  // -- Satellite records ------------------------------------------------
  setAddress: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.put<EmployeeRecord>(`${root}/${id}/address`, values),

  setBankDetail: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.put<EmployeeRecord>(`${root}/${id}/bank`, values),

  setIdentification: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.put<EmployeeRecord>(`${root}/${id}/identification`, values),

  // -- Lifecycle --------------------------------------------------------
  confirm: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/confirm`, values),

  transfer: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/transfer`, values),

  changeDesignation: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/designation`, values),

  changeManager: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/manager`, values),

  changeLocation: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/location`, values),

  promote: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/promote`, values),

  changeStatus: (id: string, values: unknown): Promise<EmployeeRecord> =>
    api.post<EmployeeRecord>(`${root}/${id}/status`, values),

  activate: (id: string): Promise<EmployeeRecord> => api.post<EmployeeRecord>(`${root}/${id}/activate`),

  deactivate: (id: string): Promise<EmployeeRecord> => api.post<EmployeeRecord>(`${root}/${id}/deactivate`),

  archive: (id: string): Promise<EmployeeRecord> => api.post<EmployeeRecord>(`${root}/${id}/archive`),

  restore: (id: string): Promise<EmployeeRecord> => api.post<EmployeeRecord>(`${root}/${id}/restore`),

  /**
   * Download the directory.
   *
   * Bypasses the `api` helper because the response is a file rather than the
   * standard envelope: it needs the raw axios response for both the body and
   * the Content-Disposition header.
   */
  export: async (query: EmployeeListQuery, format: ExportFormat): Promise<ExportResult> => {
    const response = await apiClient.get<Blob>(endpoints.employees.export, {
      params: { ...toQueryParams(query), format },
      responseType: 'blob',
    });

    return {
      blob: response.data,
      filename: filenameFrom(
        response.headers['content-disposition'] as string | undefined,
        `employees.${format}`,
      ),
    };
  },
};

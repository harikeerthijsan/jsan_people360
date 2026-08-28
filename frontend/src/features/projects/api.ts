import { api, apiClient } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type {
  Allocation,
  BenchEmployee,
  Client,
  ClientDashboardData,
  Dashboard,
  Project,
  ProjectDashboardData,
} from './types';
const root = '/projects';
export const projectsApi = {
  dashboard: () => api.get<Dashboard>(`${root}/dashboard`),
  clients: (params: Record<string, unknown>) => api.get<Page<Client>>(`${root}/clients`, { params }),
  client: (id: string) => api.get<Client>(`${root}/clients/${id}`),
  createClient: (data: unknown) => api.post<Client>(`${root}/clients`, data),
  clientDashboard: (id: string) => api.get<ClientDashboardData>(`${root}/clients/${id}/dashboard`),
  projects: (params: Record<string, unknown>) => api.get<Page<Project>>(root, { params }),
  project: (id: string) => api.get<Project>(`${root}/${id}`),
  createProject: (data: unknown) => api.post<Project>(root, data),
  projectDashboard: (id: string) => api.get<ProjectDashboardData>(`${root}/${id}/dashboard`),
  assign: (id: string, data: unknown) => api.post<Allocation>(`${root}/${id}/allocations`, data),
  change: (id: string, data: unknown) => api.post<Allocation>(`${root}/allocations/${id}/change`, data),
  remove: (id: string, data: unknown) => api.post<Allocation>(`${root}/allocations/${id}/remove`, data),
  bench: () => api.get<BenchEmployee[]>(`${root}/bench`),

  /**
   * Download a report.
   *
   * Goes through the authenticated client and saves the bytes rather than
   * pointing the browser at the URL: the endpoint needs a bearer token, which
   * a plain navigation would not carry.
   */
  exportReport: async (report: string, fmt: 'csv' | 'xlsx'): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/reports/export`, {
      params: { report, fmt },
      responseType: 'blob',
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${report}.${fmt}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

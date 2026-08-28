import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type { Dashboard, Requisition } from './types';
const root = endpoints.requisitions.root;
export const requisitionsApi = {
  list: (params: Record<string, unknown>) => api.get<Page<Requisition>>(root, { params }),
  get: (id: string) => api.get<Requisition>(`${root}/${id}`),
  create: (data: unknown) => api.post<Requisition>(root, data),
  update: (id: string, data: unknown) => api.put<Requisition>(`${root}/${id}`, data),
  dashboard: () => api.get<Dashboard>(endpoints.requisitions.dashboard),
  submit: (id: string) => api.post<Requisition>(`${root}/${id}/submit`),
  act: (id: string, action: string, comments: string | null) =>
    api.post<Requisition>(`${root}/${id}/${action}`, { comments }),
  attach: (id: string, document_id: string, attachment_type: string) =>
    api.post(`${root}/${id}/attachments`, { document_id, attachment_type }),

  /**
   * Download the register as a spreadsheet.
   *
   * Goes through the authenticated client and saves the bytes rather than
   * pointing the browser at the URL: the endpoint needs a bearer token, which
   * a plain navigation would not carry.
   */
  exportExcel: async (): Promise<void> => {
    const response = await apiClient.get<Blob>(endpoints.requisitions.export, {
      params: { format: 'xlsx' },
      responseType: 'blob',
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'requisitions.xlsx';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type { Interview, InterviewDashboard } from './types';
const root = '/interviews';
export const interviewsApi = {
  dashboard: () => api.get<InterviewDashboard>(`${root}/dashboard`),
  list: (params: Record<string, unknown>) => api.get<Page<Interview>>(root, { params }),
  get: (id: string) => api.get<Interview>(`${root}/${id}`),
  schedule: (data: unknown) => api.post<Interview>(root, data),
  update: (id: string, data: unknown) => api.put<Interview>(`${root}/${id}`, data),
  reschedule: (id: string, data: unknown) => api.post<Interview>(`${root}/${id}/reschedule`, data),
  cancel: (id: string, comments: string) => api.post<Interview>(`${root}/${id}/cancel`, { comments }),
  feedback: (id: string, data: unknown) => api.post<Interview>(`${root}/${id}/feedback`, data),
  decision: (id: string, data: unknown) => api.post<Interview>(`${root}/${id}/decision`, data),
  attachment: (id: string, data: unknown) => api.post(`${root}/${id}/attachments`, data),
};

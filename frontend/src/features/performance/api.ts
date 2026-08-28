import { api, apiClient } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';

import type {
  EmployeePerformance,
  ExportFormat,
  Feedback,
  FinalReview,
  Goal,
  ManagerReview,
  PerformanceAnalytics,
  PerformanceCycle,
  PerformanceCycleStatus,
  PerformanceDashboard,
  PerformanceHistoryEntry,
  PerformanceReport,
  Recognition,
  SelfReview,
} from './types';

/** Transport for the Performance Management endpoints. */

const root = '/performance';

export const performanceApi = {
  dashboard: (cycleId?: string) =>
    api.get<PerformanceDashboard>(`${root}/dashboard`, {
      params: cycleId ? { cycle_id: cycleId } : undefined,
    }),

  analytics: (cycleId?: string) =>
    api.get<PerformanceAnalytics>(`${root}/analytics`, {
      params: cycleId ? { cycle_id: cycleId } : undefined,
    }),

  // -- Cycles ------------------------------------------------------------
  cycles: (params: Record<string, unknown>) => api.get<Page<PerformanceCycle>>(`${root}/cycles`, { params }),
  cycle: (id: string) => api.get<PerformanceCycle>(`${root}/cycles/${id}`),
  createCycle: (data: unknown) => api.post<PerformanceCycle>(`${root}/cycles`, data),
  updateCycle: (id: string, data: unknown) => api.patch<PerformanceCycle>(`${root}/cycles/${id}`, data),
  setCycleStatus: (id: string, status: PerformanceCycleStatus) =>
    api.post<PerformanceCycle>(`${root}/cycles/${id}/status/${status}`),

  // -- Goals -------------------------------------------------------------
  goals: (params: Record<string, unknown>) => api.get<Page<Goal>>(`${root}/goals`, { params }),
  goal: (id: string) => api.get<Goal>(`${root}/goals/${id}`),
  assignGoal: (data: unknown) => api.post<Goal>(`${root}/goals`, data),
  updateGoal: (id: string, data: unknown) => api.patch<Goal>(`${root}/goals/${id}`, data),
  recordProgress: (id: string, data: unknown) => api.post<Goal>(`${root}/goals/${id}/progress`, data),

  // -- Reviews -----------------------------------------------------------
  employeePerformance: (cycleId: string, employeeId: string) =>
    api.get<EmployeePerformance>(`${root}/reviews/${cycleId}/${employeeId}`),
  submitSelfReview: (cycleId: string, employeeId: string, data: unknown) =>
    api.post<SelfReview>(`${root}/reviews/${cycleId}/${employeeId}/self`, data),
  submitManagerReview: (cycleId: string, employeeId: string, data: unknown) =>
    api.post<ManagerReview>(`${root}/reviews/${cycleId}/${employeeId}/manager`, data),
  finalise: (cycleId: string, employeeId: string, data: unknown) =>
    api.post<FinalReview>(`${root}/reviews/${cycleId}/${employeeId}/finalise`, data),

  // -- Recognition, feedback, history -------------------------------------
  recognitions: (params: Record<string, unknown>) =>
    api.get<Page<Recognition>>(`${root}/recognitions`, { params }),
  addRecognition: (data: unknown) => api.post<Recognition>(`${root}/recognitions`, data),
  feedback: (params: Record<string, unknown>) => api.get<Page<Feedback>>(`${root}/feedback`, { params }),
  addFeedback: (data: unknown) => api.post<Feedback>(`${root}/feedback`, data),
  history: (employeeId: string) => api.get<PerformanceHistoryEntry[]>(`${root}/history/${employeeId}`),

  /**
   * Download a report.
   *
   * Goes through the authenticated client and saves the bytes, rather than
   * pointing the browser at the URL: the endpoint needs a bearer token, which a
   * plain navigation would not carry.
   */
  exportReport: async (report: PerformanceReport, fmt: ExportFormat, cycleId?: string): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/reports/export`, {
      params: { report, fmt, ...(cycleId ? { cycle_id: cycleId } : {}) },
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

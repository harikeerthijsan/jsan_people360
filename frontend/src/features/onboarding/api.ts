import { api, apiClient } from '@/lib/api/client';
import type { OnboardingCase, OnboardingDashboardData, PortalData, WelcomeData } from './types';
const root = '/onboarding';
export const onboardingApi = {
  dashboard: () => api.get<OnboardingDashboardData>(`${root}/dashboard`),
  start: (data: unknown) => api.post<PortalData>(`${root}/profiles`, data),
  portal: (id: string) => api.get<PortalData>(`${root}/profiles/${id}`),
  update: (id: string, data: unknown) => api.put<PortalData>(`${root}/profiles/${id}`, data),
  acknowledge: (id: string, data: unknown) => api.post(`${root}/profiles/${id}/policies`, data),
  reviewDocument: (profileId: string, documentId: string, data: unknown) =>
    api.post(`${root}/profiles/${profileId}/documents/${documentId}/review`, data),
  approve: (id: string) => api.post<PortalData>(`${root}/profiles/${id}/approve`),
  convert: (id: string, data: unknown) => api.post(`${root}/profiles/${id}/convert`, data),
  createCase: (id: string, data: unknown) => api.post<OnboardingCase>(`${root}/profiles/${id}/case`, data),
  updateTask: (id: string, data: unknown) => api.patch(`${root}/tasks/${id}`, data),
  complete: (id: string) => api.post<OnboardingCase>(`${root}/cases/${id}/complete`),
  case: (id: string) => api.get<OnboardingCase>(`${root}/cases/${id}`),
  welcome: (id: string) => api.get<WelcomeData>(`${root}/cases/${id}/welcome`),

  /**
   * Download the readiness report.
   *
   * Goes through the authenticated client and saves the bytes rather than
   * pointing the browser at the URL: the endpoint needs a bearer token, which
   * a plain navigation would not carry.
   */
  exportReport: async (fmt: 'csv' | 'xlsx'): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/reports/export`, {
      params: { fmt },
      responseType: 'blob',
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `onboarding-report.${fmt}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

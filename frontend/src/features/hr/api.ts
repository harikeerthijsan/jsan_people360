import { api } from '@/lib/api/client';
import type {
  AttendanceRow,
  DocumentRow,
  HrAnalytics,
  HrDashboard,
  HrEmployee,
  HrPerformanceSection,
  HrProfile,
  HrProjectsSection,
  LeavePolicy,
  LeaveRow,
  Paged,
  Report,
  TimesheetRow,
} from './types';

const root = '/hr';
export const hrApi = {
  dashboard: () => api.get<HrDashboard>(`${root}/dashboard`),
  analytics: () => api.get<HrAnalytics>(`${root}/analytics`),
  employees: (params: Record<string, unknown>) => api.get<Paged<HrEmployee>>(`${root}/employees`, { params }),
  employee: (id: string) => api.get<HrProfile>(`${root}/employees/${id}`),
  attendance: (params: Record<string, unknown>) =>
    api.get<Paged<AttendanceRow>>(`${root}/attendance`, { params }),
  leave: (params: Record<string, unknown>) => api.get<Paged<LeaveRow>>(`${root}/leave`, { params }),
  policies: () => api.get<LeavePolicy[]>(`${root}/leave/policies`),
  timesheets: (params: Record<string, unknown>) =>
    api.get<Paged<TimesheetRow>>(`${root}/timesheets`, { params }),
  documents: (params: Record<string, unknown>) =>
    api.get<Paged<DocumentRow>>(`${root}/documents`, { params }),
  projects: () => api.get<HrProjectsSection>(`${root}/projects`),
  performance: () => api.get<HrPerformanceSection>(`${root}/performance`),
  reports: () => api.get<Report[]>(`${root}/reports`),
  exportUrl: (key: string) => `${root}/reports/${key}/export`,
};

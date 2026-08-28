import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  ApprovalDecision,
  ManagerDashboard,
  Regularization,
  LeaveRequest,
  TeamAttendanceRow,
  TeamCalendar,
  TeamDocumentStatus,
  TeamLeaveRow,
  TeamMember,
  TeamMemberProfile,
  TeamPerformance,
  TeamProject,
  TeamRegularizationRow,
  TeamTimesheetRow,
  Timesheet,
} from './types';

/**
 * Transport for the manager screens.
 *
 * No call carries a manager id -- there is nowhere to put one. The server
 * resolves the team from the signed-in user's reporting line, so a component
 * that passed the wrong id around could not reach another manager's team even
 * if it tried.
 *
 * The one id a caller does supply is a team member's, on the profile route, and
 * the server checks it against the reporting line before reading anything.
 */

const root = endpoints.manager.root;

export const managerApi = {
  dashboard: () => api.get<ManagerDashboard>(`${root}/dashboard`),

  // -- The team ----------------------------------------------------------
  team: (params: Record<string, unknown>) => api.get<Page<TeamMember>>(`${root}/team`, { params }),
  member: (employeeId: string) => api.get<TeamMemberProfile>(`${root}/team/${employeeId}`),

  // -- Attendance --------------------------------------------------------
  attendance: (params: Record<string, unknown>) =>
    api.get<Page<TeamAttendanceRow>>(`${root}/attendance`, { params }),
  regularizations: (params: Record<string, unknown>) =>
    api.get<Page<TeamRegularizationRow>>(`${root}/attendance/regularizations`, { params }),
  decideRegularization: (id: string, decision: ApprovalDecision) =>
    api.post<Regularization>(`${root}/attendance/regularizations/${id}/decide`, decision),

  // -- Leave -------------------------------------------------------------
  leave: (params: Record<string, unknown>) => api.get<Page<TeamLeaveRow>>(`${root}/leave`, { params }),
  decideLeave: (id: string, decision: ApprovalDecision) =>
    api.post<LeaveRequest>(`${root}/leave/${id}/decide`, decision),

  // -- Timesheets --------------------------------------------------------
  timesheets: (params: Record<string, unknown>) =>
    api.get<Page<TeamTimesheetRow>>(`${root}/timesheets`, { params }),
  timesheet: (id: string) => api.get<Timesheet>(`${root}/timesheets/${id}`),
  decideTimesheet: (id: string, decision: ApprovalDecision) =>
    api.post<Timesheet>(`${root}/timesheets/${id}/decide`, decision),

  // -- Projects, performance, calendar and documents ---------------------
  projects: () => api.get<TeamProject[]>(`${root}/projects`),
  performance: (cycleId?: string) =>
    api.get<TeamPerformance[]>(`${root}/performance`, {
      params: cycleId ? { cycle_id: cycleId } : undefined,
    }),
  calendar: (year: number, month: number) =>
    api.get<TeamCalendar>(`${root}/calendar`, { params: { year, month } }),
  documentStatus: () => api.get<TeamDocumentStatus[]>(`${root}/documents`),
};

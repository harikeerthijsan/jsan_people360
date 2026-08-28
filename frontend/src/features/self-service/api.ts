import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  AttendanceRecord,
  LeaveRequest,
  LeaveType,
  MyAttendanceSummary,
  MyAttendanceToday,
  MyDashboard,
  MyDocument,
  MyDocumentType,
  MyHoliday,
  MyLeaveBalance,
  MyProfile,
  MyProject,
  MyTimesheetWeek,
  Timesheet,
} from './types';

/**
 * Transport for the employee portal.
 *
 * Every call is to a `/me` path and none of them takes an employee id -- there
 * is nowhere to put one. That is not a convention this file is following: the
 * endpoints have no such parameter, so a screen cannot accidentally request
 * somebody else's data even if a component passed the wrong id around.
 */

const root = endpoints.me.root;

/** One square of the attendance calendar, as the workforce module models it. */
export interface CalendarDay {
  day: string;
  is_weekend: boolean;
  holiday_name: string | null;
  attendance_status: string | null;
  worked_minutes: number;
  leave_type: string | null;
  timesheet_hours: string;
}

export interface Regularization {
  id: string;
  employee_id: string;
  attendance_date: string;
  requested_check_in_at: string | null;
  requested_check_out_at: string | null;
  reason: string;
  supporting_document_id: string | null;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  decided_by_id: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  created_at: string;
}

/** Save a Blob the browser has already been handed, under a given name. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const selfServiceApi = {
  // -- Identity ----------------------------------------------------------
  profile: () => api.get<MyProfile>(root),
  dashboard: () => api.get<MyDashboard>(`${root}/dashboard`),
  updateProfile: (data: unknown) => api.patch<MyProfile>(`${root}/profile`, data),
  setAddress: (data: unknown) => api.put<MyProfile>(`${root}/profile/address`, data),

  // -- Attendance --------------------------------------------------------
  today: () => api.get<MyAttendanceToday>(`${root}/attendance/today`),
  checkIn: (data: unknown) => api.post<AttendanceRecord>(`${root}/attendance/check-in`, data),
  checkOut: (data: unknown) => api.post<AttendanceRecord>(`${root}/attendance/check-out`, data),
  attendance: (params: Record<string, unknown>) =>
    api.get<Page<AttendanceRecord>>(`${root}/attendance`, { params }),
  attendanceSummary: (fromDate: string, toDate: string) =>
    api.get<MyAttendanceSummary>(`${root}/attendance/summary`, {
      params: { from_date: fromDate, to_date: toDate },
    }),
  calendar: (year: number, month: number) =>
    api.get<CalendarDay[]>(`${root}/attendance/calendar`, { params: { year, month } }),
  regularizations: (params: Record<string, unknown>) =>
    api.get<Page<Regularization>>(`${root}/attendance/regularizations`, { params }),
  requestRegularization: (data: unknown) =>
    api.post<Regularization>(`${root}/attendance/regularization`, data),

  // -- Leave -------------------------------------------------------------
  leaveBalance: (year?: number) =>
    api.get<MyLeaveBalance[]>(`${root}/leave/balance`, { params: year ? { year } : undefined }),
  leaveTypes: () => api.get<LeaveType[]>(`${root}/leave/types`),
  leave: (params: Record<string, unknown>) => api.get<Page<LeaveRequest>>(`${root}/leave`, { params }),
  applyForLeave: (data: unknown) => api.post<LeaveRequest>(`${root}/leave`, data),
  cancelLeave: (id: string) => api.post<LeaveRequest>(`${root}/leave/${id}/cancel`),

  // -- Timesheets --------------------------------------------------------
  currentWeek: (weekStart?: string) =>
    api.get<MyTimesheetWeek>(`${root}/timesheets/current`, {
      params: weekStart ? { week_start: weekStart } : undefined,
    }),
  timesheets: (params: Record<string, unknown>) => api.get<Page<Timesheet>>(`${root}/timesheets`, { params }),
  timesheet: (id: string) => api.get<Timesheet>(`${root}/timesheets/${id}`),
  saveTimesheet: (data: unknown) => api.post<Timesheet>(`${root}/timesheets`, data),
  submitTimesheet: (id: string) => api.post<Timesheet>(`${root}/timesheets/${id}/submit`),

  // -- Documents ---------------------------------------------------------
  documents: (params: Record<string, unknown>) => api.get<Page<MyDocument>>(`${root}/documents`, { params }),
  document: (id: string) => api.get<MyDocument>(`${root}/documents/${id}`),
  documentTypes: () => api.get<MyDocumentType[]>(`${root}/documents/types`),

  uploadDocument: (form: FormData) =>
    api.post<MyDocument>(`${root}/documents`, form, {
      // Left to the browser: it has to append the multipart boundary, and a
      // hand-written header omits it.
      headers: { 'Content-Type': undefined },
    }),

  replaceDocument: (id: string, form: FormData) =>
    api.post<MyDocument>(`${root}/documents/${id}/replace`, form, {
      headers: { 'Content-Type': undefined },
    }),

  /**
   * Download through the authenticated client rather than by navigating.
   *
   * A plain link would not carry the bearer token, so the browser would be sent
   * to a 401 page instead of a file.
   */
  downloadDocument: async (id: string, filename: string): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/documents/${id}/download`, {
      responseType: 'blob',
    });
    saveBlob(response.data, filename);
  },

  /** An object URL for inline preview. The caller revokes it when done. */
  previewDocument: async (id: string): Promise<string> => {
    const response = await apiClient.get<Blob>(`${root}/documents/${id}/preview`, {
      responseType: 'blob',
    });
    return URL.createObjectURL(response.data);
  },

  // -- Projects and holidays --------------------------------------------
  projects: () => api.get<MyProject[]>(`${root}/projects`),
  holidays: (year?: number) =>
    api.get<MyHoliday[]>(`${root}/holidays`, { params: year ? { year } : undefined }),
};

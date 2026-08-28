import { api, apiClient } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';

import type {
  AttendanceRecord,
  CalendarDay,
  EmployeeShift,
  ExportFormat,
  HolidayCalendar,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  Regularization,
  Shift,
  Timesheet,
  TimesheetDashboard,
  WorkforceDashboard,
  WorkforceReport,
} from './types';

/** Transport for the Workforce Operations endpoints. */

const root = '/workforce';

export const workforceApi = {
  dashboard: (on?: string) =>
    api.get<WorkforceDashboard>(`${root}/dashboard`, { params: on ? { on } : undefined }),

  timesheetDashboard: (weekStart?: string) =>
    api.get<TimesheetDashboard>(`${root}/timesheets/dashboard`, {
      params: weekStart ? { week_start: weekStart } : undefined,
    }),

  calendar: (employeeId: string, year: number, month: number) =>
    api.get<CalendarDay[]>(`${root}/calendar/${employeeId}`, { params: { year, month } }),

  // -- Shifts ------------------------------------------------------------
  shifts: (params: Record<string, unknown>) => api.get<Page<Shift>>(`${root}/shifts`, { params }),
  createShift: (data: unknown) => api.post<Shift>(`${root}/shifts`, data),
  updateShift: (id: string, data: unknown) => api.patch<Shift>(`${root}/shifts/${id}`, data),
  assignShift: (data: unknown) => api.post<EmployeeShift>(`${root}/shifts/assign`, data),
  shiftHistory: (employeeId: string) => api.get<EmployeeShift[]>(`${root}/shifts/history/${employeeId}`),

  // -- Attendance --------------------------------------------------------
  attendance: (params: Record<string, unknown>) =>
    api.get<Page<AttendanceRecord>>(`${root}/attendance`, { params }),
  checkIn: (employeeId: string, data: unknown) =>
    api.post<AttendanceRecord>(`${root}/attendance/${employeeId}/check-in`, data),
  checkOut: (employeeId: string, data: unknown) =>
    api.post<AttendanceRecord>(`${root}/attendance/${employeeId}/check-out`, data),

  regularizations: (params: Record<string, unknown>) =>
    api.get<Page<Regularization>>(`${root}/regularizations`, { params }),
  requestRegularization: (employeeId: string, data: unknown) =>
    api.post<Regularization>(`${root}/regularizations/${employeeId}`, data),
  decideRegularization: (id: string, data: unknown) =>
    api.post<Regularization>(`${root}/regularizations/${id}/decide`, data),

  // -- Leave -------------------------------------------------------------
  leaveTypes: () => api.get<LeaveType[]>(`${root}/leave/types`),
  createLeaveType: (data: unknown) => api.post<LeaveType>(`${root}/leave/types`, data),
  updateLeaveType: (id: string, data: unknown) => api.patch<LeaveType>(`${root}/leave/types/${id}`, data),
  leaveBalances: (employeeId: string, year?: number) =>
    api.get<LeaveBalance[]>(`${root}/leave/balances/${employeeId}`, {
      params: year ? { year } : undefined,
    }),
  leaveRequests: (params: Record<string, unknown>) =>
    api.get<Page<LeaveRequest>>(`${root}/leave`, { params }),
  applyForLeave: (employeeId: string, data: unknown) =>
    api.post<LeaveRequest>(`${root}/leave/${employeeId}`, data),
  decideLeave: (id: string, data: unknown) => api.post<LeaveRequest>(`${root}/leave/${id}/decide`, data),
  cancelLeave: (id: string) => api.post<LeaveRequest>(`${root}/leave/${id}/cancel`),

  // -- Holidays ----------------------------------------------------------
  holidayCalendars: (params: Record<string, unknown>) =>
    api.get<HolidayCalendar[]>(`${root}/holidays`, { params }),
  createHolidayCalendar: (data: unknown) => api.post<HolidayCalendar>(`${root}/holidays`, data),

  // -- Timesheets --------------------------------------------------------
  timesheets: (params: Record<string, unknown>) => api.get<Page<Timesheet>>(`${root}/timesheets`, { params }),
  timesheet: (id: string) => api.get<Timesheet>(`${root}/timesheets/${id}`),
  saveTimesheet: (employeeId: string, data: unknown) =>
    api.post<Timesheet>(`${root}/timesheets/${employeeId}`, data),
  submitTimesheet: (id: string) => api.post<Timesheet>(`${root}/timesheets/${id}/submit`),
  decideTimesheet: (id: string, data: unknown) =>
    api.post<Timesheet>(`${root}/timesheets/${id}/decide`, data),

  /**
   * Download a report.
   *
   * Goes through the authenticated client and saves the bytes rather than
   * pointing the browser at the URL: the endpoint needs a bearer token, which a
   * plain navigation would not carry.
   */
  exportReport: async (
    report: WorkforceReport,
    fmt: ExportFormat,
    fromDate: string,
    toDate: string,
  ): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/reports/export`, {
      params: { report, fmt, from_date: fromDate, to_date: toDate },
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

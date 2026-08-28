import { env } from '@/lib/env';

/** Static product metadata used across the shell and document head. */
export const siteConfig = {
  name: env.NEXT_PUBLIC_APP_NAME,
  shortName: 'People360',
  description: 'Enterprise HR management platform for the complete employee lifecycle.',
  company: 'JSAN Technologies',
  environment: env.NEXT_PUBLIC_APP_ENV,
} as const;

export const routes = {
  home: '/',
  dashboard: '/dashboard',
  organization: '/organization',
  users: '/users',
  roles: '/roles',
  employees: '/employees',
  employeeDashboard: '/employees/dashboard',
  documents: '/documents',
  documentDashboard: '/documents/dashboard',
  documentSettings: '/documents/settings',
  requisitions: '/requisitions',
  requisitionDashboard: '/requisitions/dashboard',
  recruitment: '/recruitment',
  interviews: '/interviews',
  offers: '/offers',
  offerDashboard: '/offers/dashboard',
  offerTemplates: '/offers/templates',
  onboarding: '/onboarding',
  projects: '/projects',
  clients: '/clients',
  attendance: '/attendance',
  attendanceRegister: '/attendance/register',
  attendanceCalendar: '/attendance/calendar',
  attendanceRegularizations: '/attendance/regularizations',
  workforceReports: '/attendance/reports',
  shifts: '/shifts',
  shiftAssignments: '/shifts/assignments',
  leave: '/leave',
  leaveApprovals: '/leave/approvals',
  leaveTypes: '/leave/types',
  holidays: '/leave/holidays',
  timesheets: '/timesheets',
  timesheetApprovals: '/timesheets/approvals',
  /**
   * The employee portal.
   *
   * Under `/employee` rather than mixed into the HR routes above: the two
   * answer different questions about the same data -- "the company's leave" and
   * "my leave" -- and a shared URL would make it impossible to tell from a link
   * which one somebody was sent.
   *
   * Named `my*` for the same reason. `employeeDashboard` above is HR's view of
   * the workforce; these are the employee's view of themselves, and two keys
   * that read alike would be picked wrongly sooner or later.
   */
  myDashboard: '/employee/dashboard',
  myAttendance: '/employee/attendance',
  myLeave: '/employee/leave',
  myTimesheets: '/employee/timesheets',
  myDocuments: '/employee/documents',
  myProjects: '/employee/projects',
  myHolidays: '/employee/holidays',
  myProfile: '/employee/profile',
  myResignation: '/employee/resignation',
  myExitInterview: '/employee/exit-interview',
  myOffboarding: '/employee/offboarding',
  myAssets: '/employee/assets',
  myHelpdesk: '/employee/helpdesk',
  myAnnouncements: '/employee/announcements',
  myPayroll: '/employee/payroll',
  myPayslips: '/employee/payroll/payslips',
  myPayslip: (payslipId: string): string => `/employee/payroll/payslips/${payslipId}`,

  /**
   * The manager's team.
   *
   * Under `/manager` for the same reason the portal is under `/employee`: the
   * HR screens, the employee portal and the team screens answer three different
   * questions about the same rows -- "the company's leave", "my leave" and "my
   * team's leave" -- and one shared URL would make a pasted link ambiguous
   * about which of the three somebody was being sent to.
   */
  managerDashboard: '/manager/dashboard',
  managerTeam: '/manager/team',
  managerAttendance: '/manager/attendance',
  managerRegularization: '/manager/attendance/regularization',
  managerLeave: '/manager/leave',
  managerTimesheets: '/manager/timesheets',
  managerProjects: '/manager/projects',
  managerPerformance: '/manager/performance',
  managerCalendar: '/manager/calendar',
  managerDocuments: '/manager/documents',
  managerOffboarding: '/manager/offboarding',
  managerAssets: '/manager/assets',

  hrDashboard: '/hr/dashboard',
  hrEmployees: '/hr/employees',
  hrAttendance: '/hr/attendance',
  hrLeave: '/hr/leave',
  hrLeavePolicies: '/hr/leave/policies',
  hrTimesheets: '/hr/timesheets',
  hrProjects: '/hr/projects',
  hrDocuments: '/hr/documents',
  hrPerformance: '/hr/performance',
  hrRecruitment: '/hr/recruitment',
  hrHelpdesk: '/hr/helpdesk',
  hrAnnouncements: '/hr/announcements',
  hrOffboarding: '/hr/offboarding',
  hrAssets: '/hr/assets',
  hrReports: '/hr/reports',

  /**
   * Asset management.
   *
   * Under `/admin` rather than beside the HR screens: the register is IT and
   * Admin property management, and the URL says whose job it is.
   */
  assets: '/admin/assets',
  assetNew: '/admin/assets/new',
  assetDashboard: '/admin/assets/dashboard',
  assetMaintenance: '/admin/assets/maintenance',
  assetReports: '/admin/assets/reports',
  assetDetail: (assetId: string): string => `/admin/assets/${assetId}`,

  /**
   * Payroll administration.
   *
   * Under `/admin` like the asset register: configuring pay is an
   * administrative act, and the URL says whose job it is. An employee's own
   * compensation is under `/employee/payroll` with the rest of the portal.
   */
  payrollEmployees: '/admin/payroll/employees',
  payrollStructures: '/admin/payroll/salary-structures',
  payrollComponents: '/admin/payroll/components',
  payrollEmployeeSalary: (employeeId: string): string => `/admin/payroll/employees/${employeeId}/salary`,
  payrollSettings: '/admin/payroll/settings',
  payrollPeriods: '/admin/payroll/periods',
  payrollRules: '/admin/payroll/rules',
  payrollEmployeeSettings: '/admin/payroll/employee-settings',
  payrollInputs: '/admin/payroll/inputs',
  payrollInputDetail: (employeeId: string, periodId: string): string =>
    `/admin/payroll/inputs/${employeeId}?period=${periodId}`,
  payrollRuns: '/admin/payroll/runs',
  payrollRunDetail: (runId: string): string => `/admin/payroll/runs/${runId}`,
  payrollRunEmployee: (runId: string, employeeId: string): string =>
    `/admin/payroll/runs/${runId}/employees/${employeeId}`,
  payrollReview: '/admin/payroll/review',
  payrollRunReview: (runId: string): string => `/admin/payroll/runs/${runId}/review`,
  payrollRunReconciliation: (runId: string): string =>
    `/admin/payroll/runs/${runId}/reconciliation`,
  payrollApproval: '/admin/payroll/approval',
  payrollRunApproval: (runId: string): string => `/admin/payroll/runs/${runId}/approval`,
  payrollHistory: '/admin/payroll/history',
  payrollPayslips: '/admin/payroll/payslips',
  payrollReports: '/admin/payroll/reports',
  payrollSettlements: '/admin/payroll/final-settlement',
  payrollSettlement: (settlementId: string): string => `/admin/payroll/final-settlement/${settlementId}`,
  mySettlement: '/employee/payroll/settlement',
  payrollEmployeePayslip: (employeeId: string, payslipId: string): string =>
    `/admin/payroll/employees/${employeeId}/payslips/${payslipId}`,

  /**
   * The helpdesk.
   *
   * `/hr/helpdesk` is the agent's queue, and it stays under `/hr` because that
   * is where it already was -- the screen that lived there was a placeholder
   * for exactly this. An employee's own requests are under `/employee`, for the
   * same reason every other portal page is.
   */
  helpdeskTicket: (ticketId: string): string => `/hr/helpdesk/${ticketId}`,

  performance: '/performance',
  auditTrail: '/admin/audit',
  profile: '/profile',
  settings: '/settings',
  login: '/login',
  forgotPassword: '/forgot-password',
  resetPassword: '/reset-password',
} as const;

import {
  Banknote,
  DoorOpen,
  FileSpreadsheet,
  LifeBuoy,
  Laptop,
  Megaphone,
  Award,
  Boxes,
  BriefcaseBusiness,
  Building2,
  CalendarClock,
  CalendarDays,
  CalendarOff,
  ClipboardCheck,
  Clock,
  FileClock,
  FileBadge,
  FileText,
  Gauge,
  Layers,
  LayoutDashboard,
  LogOut,
  MapPin,
  Settings,
  ShieldCheck,
  TrendingUp,
  UserCog,
  UserRoundPlus,
  Users,
  Users2,
  Wallet,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import { routes } from '@/config/site';

export interface NavItem {
  /** Stable identifier, also used as the React key. */
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  /**
   * Modules that ship in later phases are listed but disabled, so the
   * information architecture is visible from day one and adding a module means
   * flipping this flag rather than redesigning the shell.
   */
  disabled?: boolean;
  badge?: string;
  /**
   * Highlight this item only on an exact path match.
   *
   * Needed for section landing pages: `/organization` is a prefix of every
   * master route, so without this both "Overview" and the master would be
   * marked as the current page at once.
   */
  exact?: boolean;
  /**
   * Label to use when this route appears as an *ancestor* in a breadcrumb.
   *
   * A section landing page is called "Overview" in the sidebar, where its
   * section heading supplies the context. A breadcrumb has no such heading, so
   * "Overview › Grades" reads as a non-sequitur where "Organization › Grades"
   * does not.
   */
  breadcrumbLabel?: string;
  /**
   * Permission required to see this item.
   *
   * Absent means "any signed-in user", which is the right default for personal
   * pages -- your own profile, your own settings. Everything that reads other
   * people's data names one, and the sidebar drops what the session cannot open
   * rather than offering a link that answers 403.
   */
  permission?: string;
  /**
   * Every one of these is required, on top of `permission`.
   *
   * For the handful of screens whose audience is an intersection rather than a
   * single grant. Team document completion is the case that needed it: on its
   * own `documents:view` is a permission every employee holds, so the item has
   * to ask for `employees:view` as well or it would appear in a sidebar with
   * nothing else in its section.
   */
  allOf?: string[];
}

export interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

export const navigation: NavSection[] = [
  {
    id: 'overview',
    label: 'Overview',
    items: [{ id: 'dashboard', label: 'Dashboard', href: routes.dashboard, icon: LayoutDashboard }],
  },
  {
    // First after the dashboard, and permission-free throughout.
    //
    // These are the pages every signed-in person has, about themselves. A
    // permission on them would let an administrator take away somebody's
    // ability to see their own attendance, which is not a thing anybody wants
    // to be able to do -- so the server guards them by identity instead, and
    // the sidebar mirrors that by asking for nothing.
    id: 'self-service',
    label: 'My Workspace',
    items: [
      {
        id: 'my-dashboard',
        label: 'My Dashboard',
        href: routes.myDashboard,
        icon: LayoutDashboard,
      },
      { id: 'my-attendance', label: 'My Attendance', href: routes.myAttendance, icon: CalendarClock },
      { id: 'my-leave', label: 'My Leave', href: routes.myLeave, icon: CalendarOff },
      { id: 'my-timesheets', label: 'My Timesheets', href: routes.myTimesheets, icon: FileClock },
      { id: 'my-documents', label: 'My Documents', href: routes.myDocuments, icon: FileText },
      { id: 'my-projects', label: 'My Projects', href: routes.myProjects, icon: BriefcaseBusiness },
      { id: 'my-holidays', label: 'My Holidays', href: routes.myHolidays, icon: CalendarDays },
      { id: 'my-profile', label: 'My Profile', href: routes.myProfile, icon: UserCog },
      {
        id: 'my-resignation',
        label: 'My Resignation',
        href: routes.myResignation,
        icon: LogOut,
      },
      {
        id: 'my-assets',
        label: 'My Assets',
        href: routes.myAssets,
        icon: Laptop,
      },
      {
        id: 'my-payroll',
        label: 'My Payroll',
        href: routes.myPayroll,
        icon: Wallet,
      },
      {
        id: 'my-payslips',
        label: 'My Payslips',
        href: routes.myPayslips,
        icon: FileText,
      },
      {
        id: 'my-settlement',
        label: 'My Final Settlement',
        href: routes.mySettlement,
        icon: LogOut,
      },
      {
        id: 'my-helpdesk',
        label: 'My Requests',
        href: routes.myHelpdesk,
        icon: LifeBuoy,
      },
      {
        id: 'my-announcements',
        label: 'Announcements',
        href: routes.myAnnouncements,
        icon: Megaphone,
      },
      {
        id: 'my-offboarding',
        label: 'My Offboarding',
        href: routes.myOffboarding,
        icon: DoorOpen,
      },
    ],
  },
  {
    // Directly after the personal pages, because it is the same shape of
    // question one step out: "mine", then "my team's", then the company's.
    //
    // Every item names a *manage-other-people* permission rather than a plain
    // view. The base Employee role holds `attendance:view`, `leave:view` and
    // the rest -- it must, or nobody could see their own records -- so an item
    // guarded on one of those would appear for every employee and lead them to
    // a screen the API refuses.
    id: 'manager',
    label: 'My Team',
    items: [
      {
        id: 'manager-dashboard',
        permission: 'employees:view',
        label: 'Team Dashboard',
        href: routes.managerDashboard,
        icon: Gauge,
      },
      {
        id: 'manager-team',
        permission: 'employees:view',
        label: 'Team Members',
        href: routes.managerTeam,
        icon: Users2,
      },
      {
        id: 'manager-attendance',
        permission: 'attendance:approve',
        label: 'Team Attendance',
        href: routes.managerAttendance,
        icon: CalendarClock,
        // `/manager/attendance` is a prefix of the corrections route below, so
        // without this both would be lit at once.
        exact: true,
      },
      {
        id: 'manager-regularization',
        permission: 'attendance:approve',
        label: 'Team Corrections',
        href: routes.managerRegularization,
        icon: ClipboardCheck,
      },
      {
        id: 'manager-leave',
        permission: 'leave:approve',
        label: 'Team Leave',
        href: routes.managerLeave,
        icon: CalendarOff,
      },
      {
        id: 'manager-timesheets',
        permission: 'timesheets:approve',
        label: 'Team Timesheets',
        href: routes.managerTimesheets,
        icon: FileClock,
      },
      {
        id: 'manager-assets',
        permission: 'assets:view',
        label: 'Team Assets',
        href: routes.managerAssets,
        icon: Laptop,
      },
      {
        id: 'manager-offboarding',
        permission: 'resignation:approve',
        label: 'Team Offboarding',
        href: routes.managerOffboarding,
        icon: DoorOpen,
      },
      {
        id: 'manager-projects',
        permission: 'projects:view',
        label: 'Team Projects',
        href: routes.managerProjects,
        icon: BriefcaseBusiness,
      },
      {
        id: 'manager-performance',
        permission: 'performance:create',
        label: 'Team Performance',
        href: routes.managerPerformance,
        icon: TrendingUp,
      },
      {
        id: 'manager-calendar',
        permission: 'attendance:approve',
        label: 'Team Calendar',
        href: routes.managerCalendar,
        icon: CalendarDays,
      },
      {
        id: 'manager-documents',
        permission: 'documents:view',
        allOf: ['employees:view'],
        label: 'Team Documents',
        href: routes.managerDocuments,
        icon: FileText,
      },
    ],
  },
  {
    id: 'hr',
    label: 'HR Administration',
    items: [
      {
        id: 'hr-dashboard',
        permission: 'employees:view_all',
        label: 'HR Dashboard',
        href: routes.hrDashboard,
        icon: LayoutDashboard,
      },
      {
        id: 'hr-employees',
        permission: 'employees:view_all',
        label: 'HR Employees',
        href: routes.hrEmployees,
        icon: Users,
        exact: true,
      },
      {
        id: 'hr-attendance',
        // Mirrors require_org_wide("attendance:view") on the endpoint.
        allOf: ['attendance:view', 'employees:view_all'],
        label: 'HR Attendance',
        href: routes.hrAttendance,
        icon: CalendarClock,
      },
      {
        id: 'hr-leave',
        allOf: ['leave:view', 'employees:view_all'],
        label: 'HR Leave',
        href: routes.hrLeave,
        icon: CalendarOff,
        exact: true,
      },
      {
        id: 'hr-leave-policies',
        // Configuration rather than a read: the screen exists to change policy,
        // and `leave:policy_manage` is what the write endpoints require.
        permission: 'leave:policy_manage',
        label: 'Leave Policies',
        href: routes.hrLeavePolicies,
        icon: Layers,
      },
      {
        id: 'hr-timesheets',
        allOf: ['timesheets:view', 'employees:view_all'],
        label: 'HR Timesheets',
        href: routes.hrTimesheets,
        icon: FileClock,
      },
      {
        id: 'hr-projects',
        allOf: ['projects:view', 'employees:view_all'],
        label: 'Workforce Allocation',
        href: routes.hrProjects,
        icon: BriefcaseBusiness,
      },
      {
        id: 'hr-documents',
        allOf: ['documents:view', 'employees:view_all'],
        label: 'Document Reviews',
        href: routes.hrDocuments,
        icon: FileText,
      },
      {
        id: 'hr-performance',
        allOf: ['performance:view', 'employees:view_all'],
        label: 'Performance Overview',
        href: routes.hrPerformance,
        icon: TrendingUp,
      },
      {
        id: 'hr-recruitment',
        permission: 'recruitment:view',
        label: 'HR Recruitment',
        href: routes.hrRecruitment,
        icon: UserRoundPlus,
      },
      {
        id: 'hr-helpdesk',
        // The real permission now that there is a real module behind this. It
        // used to ask for `employees:view_all` plus two unrelated views,
        // because the screen was a placeholder reading a counts endpoint.
        permission: 'helpdesk:view',
        label: 'Helpdesk',
        href: routes.hrHelpdesk,
        icon: LifeBuoy,
      },
      {
        id: 'hr-announcements',
        permission: 'announcements:view',
        label: 'Announcements',
        href: routes.hrAnnouncements,
        icon: Megaphone,
      },
      {
        id: 'hr-assets',
        permission: 'assets:view',
        label: 'Employee Assets',
        href: routes.hrAssets,
        icon: Laptop,
      },
      {
        id: 'hr-offboarding',
        permission: 'offboarding:view',
        label: 'Offboarding',
        href: routes.hrOffboarding,
        icon: DoorOpen,
      },
      {
        id: 'hr-reports',
        permission: 'reports:view',
        label: 'HR Reports',
        href: routes.hrReports,
        icon: FileText,
      },
    ],
  },
  {
    // Master data comes before the people modules because every one of them
    // references it.
    id: 'organization',
    label: 'Organization',
    items: [
      {
        id: 'organization-overview',
        permission: 'organization:view',
        label: 'Overview',
        breadcrumbLabel: 'Organization',
        href: routes.organization,
        icon: Building2,
        exact: true,
      },
      {
        id: 'organizations',
        permission: 'organization:view',
        label: 'Company Profile',
        href: `${routes.organization}/organizations`,
        icon: Building2,
      },
      {
        id: 'business-units',
        permission: 'organization:view',
        label: 'Business Units',
        href: `${routes.organization}/business-units`,
        icon: Boxes,
      },
      {
        id: 'teams',
        permission: 'organization:view',
        label: 'Teams',
        href: `${routes.organization}/teams`,
        icon: Users2,
      },
      {
        id: 'designations',
        permission: 'organization:view',
        label: 'Designations',
        href: `${routes.organization}/designations`,
        icon: FileBadge,
      },
      {
        id: 'grades',
        permission: 'organization:view',
        label: 'Grades',
        href: `${routes.organization}/grades`,
        icon: Award,
      },
      {
        id: 'locations',
        permission: 'organization:view',
        label: 'Locations',
        href: `${routes.organization}/locations`,
        icon: MapPin,
      },
      {
        id: 'employment-types',
        permission: 'organization:view',
        label: 'Employment Types',
        href: `${routes.organization}/employment-types`,
        icon: BriefcaseBusiness,
      },
    ],
  },
  {
    id: 'people',
    label: 'People',
    items: [
      {
        id: 'recruitment',
        permission: 'recruitment:view',
        label: 'Recruitment',
        href: '/recruitment',
        icon: UserRoundPlus,
      },
      {
        id: 'job-openings',
        permission: 'recruitment:view',
        label: 'Job Openings',
        href: '/recruitment/openings',
        icon: BriefcaseBusiness,
      },
      {
        id: 'candidates',
        permission: 'recruitment:view',
        label: 'Candidates',
        href: '/recruitment/candidates',
        icon: Users,
      },
      {
        id: 'recruitment-pipeline',
        permission: 'recruitment:view',
        label: 'Hiring Pipeline',
        href: '/recruitment/pipeline',
        icon: Layers,
      },
      {
        id: 'talent-pools',
        permission: 'recruitment:view',
        label: 'Talent Pools',
        href: '/recruitment/talent-pools',
        icon: Users2,
      },
      {
        id: 'interview-dashboard',
        permission: 'interviews:view',
        label: 'Interview Dashboard',
        href: '/interviews/dashboard',
        icon: LayoutDashboard,
      },
      {
        id: 'interviews',
        permission: 'interviews:view',
        label: 'Interviews',
        href: '/interviews',
        icon: CalendarClock,
        exact: true,
      },
      {
        id: 'interview-calendar',
        permission: 'interviews:view',
        label: 'Interview Calendar',
        href: '/interviews/calendar',
        icon: CalendarClock,
      },
      {
        id: 'offer-dashboard',
        permission: 'offers:view',
        label: 'Offer Dashboard',
        href: routes.offerDashboard,
        icon: Gauge,
      },
      {
        id: 'offers',
        permission: 'offers:view',
        label: 'Offers',
        href: routes.offers,
        icon: FileText,
        exact: true,
      },
      {
        id: 'offer-templates',
        permission: 'offers:view',
        label: 'Offer Templates',
        href: routes.offerTemplates,
        icon: FileBadge,
      },
      {
        id: 'onboarding',
        permission: 'onboarding:view',
        label: 'Preboarding & Onboarding',
        href: routes.onboarding,
        icon: UserRoundPlus,
      },
      {
        id: 'project-dashboard',
        permission: 'projects:view',
        label: 'Project Dashboard',
        href: routes.projects,
        icon: Gauge,
        exact: true,
      },
      {
        id: 'projects',
        permission: 'projects:view',
        label: 'Projects',
        href: `${routes.projects}/list`,
        icon: BriefcaseBusiness,
      },
      { id: 'clients', permission: 'projects:view', label: 'Clients', href: routes.clients, icon: Building2 },
      {
        id: 'bench',
        permission: 'projects:view',
        label: 'Bench Management',
        href: `${routes.projects}/bench`,
        icon: Users2,
      },
      {
        id: 'workforce-dashboard',
        permission: 'requisitions:view',
        label: 'Workforce planning',
        href: routes.requisitionDashboard,
        icon: BriefcaseBusiness,
      },
      {
        id: 'requisitions',
        permission: 'requisitions:view',
        label: 'Job Requisitions',
        href: routes.requisitions,
        icon: FileBadge,
        exact: true,
      },
      {
        id: 'employee-dashboard',
        permission: 'employees:view',
        label: 'People dashboard',
        href: '/employees/dashboard',
        icon: LayoutDashboard,
      },
      {
        id: 'employees',
        permission: 'employees:view',
        label: 'Employees',
        href: '/employees',
        icon: Users,
        // The directory is the parent of /employees/[id] and /employees/new but
        // not of /employees/dashboard, which has its own entry above.
        exact: true,
      },
      {
        id: 'performance',
        // Org-wide, so the same pairing the Workforce section uses: the plain
        // view is the floor every employee stands on.
        allOf: ['performance:view', 'employees:view_all'],
        label: 'Performance',
        href: routes.performance,
        icon: TrendingUp,
      },
    ],
  },
  {
    // Org-wide operational screens. Every item pairs its module view with
    // `employees:view_all` -- the plain views are the floor the Employee role
    // stands on (they gate seeing one's *own* records), so alone they would
    // put these screens in every employee's sidebar. The approval items are
    // gated on approve permissions, which employees never hold.
    id: 'workforce',
    label: 'Workforce',
    items: [
      {
        id: 'workforce-overview',
        allOf: ['attendance:view', 'employees:view_all'],
        label: 'Overview',
        breadcrumbLabel: 'Workforce',
        href: routes.attendance,
        icon: Gauge,
        exact: true,
      },
      {
        id: 'attendance-register',
        allOf: ['attendance:view', 'employees:view_all'],
        label: 'Attendance Register',
        href: routes.attendanceRegister,
        icon: CalendarClock,
      },
      {
        id: 'attendance-calendar',
        allOf: ['attendance:view', 'employees:view_all'],
        label: 'Attendance Calendar',
        href: routes.attendanceCalendar,
        icon: CalendarDays,
      },
      {
        id: 'attendance-regularizations',
        allOf: ['attendance:view', 'employees:view_all'],
        label: 'Corrections',
        href: routes.attendanceRegularizations,
        icon: ClipboardCheck,
      },
      {
        id: 'shifts',
        allOf: ['shifts:view', 'employees:view_all'],
        label: 'Shifts',
        href: routes.shifts,
        icon: Clock,
        exact: true,
      },
      {
        id: 'shift-assignments',
        allOf: ['shifts:view', 'employees:view_all'],
        label: 'Shift Assignments',
        href: routes.shiftAssignments,
        icon: Users2,
      },
      {
        id: 'leave',
        allOf: ['leave:view', 'employees:view_all'],
        label: 'Leave',
        href: routes.leave,
        icon: CalendarOff,
        exact: true,
      },
      {
        id: 'leave-approvals',
        permission: 'leave:approve',
        label: 'Leave Approvals',
        href: routes.leaveApprovals,
        icon: ClipboardCheck,
      },
      {
        id: 'leave-types',
        allOf: ['shifts:view', 'employees:view_all'],
        label: 'Leave Types',
        href: routes.leaveTypes,
        icon: Layers,
      },
      {
        id: 'holidays',
        allOf: ['shifts:view', 'employees:view_all'],
        label: 'Holiday Calendars',
        href: routes.holidays,
        icon: CalendarDays,
      },
      {
        id: 'timesheets',
        allOf: ['timesheets:view', 'employees:view_all'],
        label: 'Timesheets',
        href: routes.timesheets,
        icon: FileClock,
        exact: true,
      },
      {
        id: 'timesheet-approvals',
        permission: 'timesheets:approve',
        label: 'Timesheet Approvals',
        href: routes.timesheetApprovals,
        icon: ClipboardCheck,
      },
      {
        id: 'workforce-reports',
        permission: 'reports:view',
        label: 'Reports',
        href: routes.workforceReports,
        icon: FileText,
      },
    ],
  },
  {
    id: 'documents',
    label: 'Documents',
    items: [
      {
        id: 'document-dashboard',
        allOf: ['documents:view', 'employees:view_all'],
        label: 'Dashboard',
        href: routes.documentDashboard,
        icon: LayoutDashboard,
      },
      {
        id: 'document-vault',
        allOf: ['documents:view', 'employees:view_all'],
        label: 'Document Vault',
        href: routes.documents,
        icon: FileText,
        exact: true,
      },
      {
        id: 'document-settings',
        permission: 'documents:update',
        label: 'Categories & Types',
        href: routes.documentSettings,
        icon: Settings,
      },
    ],
  },
  {
    id: 'administration',
    label: 'Administration',
    items: [
      { id: 'users', permission: 'users:view', label: 'Users', href: routes.users, icon: Users },
      // The asset register sits in Administration rather than HR: it is IT and
      // Admin property management. HR reaches the one view they need -- what a
      // leaver is holding -- from their own section and from an offboarding
      // case, and holds `assets:view` and nothing else.
      {
        id: 'assets',
        permission: 'assets:view',
        label: 'Asset Register',
        href: routes.assets,
        icon: Laptop,
        exact: true,
      },
      {
        id: 'assets-dashboard',
        permission: 'assets:view',
        label: 'Asset Dashboard',
        href: routes.assetDashboard,
        icon: Gauge,
      },
      {
        id: 'assets-maintenance',
        permission: 'assets:maintain',
        label: 'Asset Maintenance',
        href: routes.assetMaintenance,
        icon: Wrench,
      },
      {
        id: 'assets-reports',
        permission: 'assets:export',
        label: 'Asset Reports',
        href: routes.assetReports,
        icon: FileSpreadsheet,
      },
      // Payroll sits in Administration with the register, and for the same
      // reason: no seeded role below Administrator holds any payroll
      // permission. HR reaches these screens only when the grants are ticked
      // on purpose, which is the module's whole access model.
      {
        id: 'payroll-employees',
        permission: 'payroll:view',
        label: 'Employee Compensation',
        href: routes.payrollEmployees,
        icon: Wallet,
      },
      {
        id: 'payroll-structures',
        permission: 'payroll:structure_manage',
        label: 'Salary Structures',
        href: routes.payrollStructures,
        icon: Layers,
      },
      {
        id: 'payroll-components',
        permission: 'payroll:component_manage',
        label: 'Salary Components',
        href: routes.payrollComponents,
        icon: Boxes,
      },
      {
        id: 'payroll-settings',
        permission: 'payroll:config_view',
        label: 'Payroll Settings',
        href: routes.payrollSettings,
        icon: Settings,
      },
      {
        id: 'payroll-periods',
        permission: 'payroll:period_manage',
        label: 'Payroll Periods',
        href: routes.payrollPeriods,
        icon: CalendarClock,
      },
      {
        id: 'payroll-rules',
        permission: 'payroll:rule_manage',
        label: 'Payroll Rules',
        href: routes.payrollRules,
        icon: ClipboardCheck,
      },
      {
        id: 'payroll-employee-settings',
        permission: 'payroll:employee_settings_view',
        label: 'Employee Payroll Settings',
        href: routes.payrollEmployeeSettings,
        icon: UserCog,
      },
      {
        id: 'payroll-inputs',
        permission: 'payroll:inputs_view',
        label: 'Payroll Inputs',
        href: routes.payrollInputs,
        icon: FileSpreadsheet,
      },
      {
        id: 'payroll-runs',
        permission: 'payroll:runs_view',
        label: 'Payroll Runs',
        href: routes.payrollRuns,
        icon: Banknote,
      },
      {
        id: 'payroll-review',
        permission: 'payroll:review_view',
        label: 'Payroll Review',
        href: routes.payrollReview,
        icon: ShieldCheck,
      },
      {
        id: 'payroll-approval',
        permission: 'payroll:approval_view',
        label: 'Payroll Approval',
        href: routes.payrollApproval,
        icon: ClipboardCheck,
      },
      {
        id: 'payroll-history',
        permission: 'payroll:finalized_view',
        label: 'Payroll History',
        href: routes.payrollHistory,
        icon: CalendarClock,
      },
      {
        id: 'payroll-payslips',
        permission: 'payroll:payslip_view',
        label: 'Payslips',
        href: routes.payrollPayslips,
        icon: FileText,
      },
      {
        id: 'payroll-reports',
        permission: 'payroll:report_view',
        label: 'Payroll Reports',
        href: routes.payrollReports,
        icon: FileSpreadsheet,
      },
      {
        id: 'payroll-settlements',
        permission: 'payroll:settlement_view',
        label: 'Final Settlement',
        href: routes.payrollSettlements,
        icon: LogOut,
      },
      {
        id: 'roles',
        permission: 'roles:view',
        label: 'Roles & Permissions',
        href: routes.roles,
        icon: ShieldCheck,
      },
      // Relabelled when the employee portal landed. This page is the *login
      // account* -- username, password, session -- and "My Workspace › My
      // Profile" is the employee record. Two sidebar entries reading "My
      // Profile" is a coin toss for the person looking for one of them.
      { id: 'profile', label: 'My Account', href: routes.profile, icon: UserCog },
      {
        id: 'settings',
        permission: 'settings:view',
        label: 'Settings',
        href: routes.settings,
        icon: Settings,
      },
      {
        id: 'audit-trail',
        permission: 'audit:view',
        label: 'Audit Trail',
        href: routes.auditTrail,
        icon: ShieldCheck,
      },
    ],
  },
];

/** Flat lookup used by the breadcrumb builder. */
export const navigationIndex: ReadonlyMap<string, NavItem> = new Map(
  navigation.flatMap((section) => section.items.map((item) => [item.href, item])),
);

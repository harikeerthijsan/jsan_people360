/**
 * Every API path in one place.
 *
 * Feature modules import from here rather than writing string literals, so a
 * backend route change is a one-line edit and typos surface at compile time.
 */
export const endpoints = {
  health: {
    live: '/health',
    ready: '/health/ready',
  },
  auth: {
    login: '/auth/login',
    logout: '/auth/logout',
    refresh: '/auth/refresh',
    me: '/auth/me',
    forgotPassword: '/auth/forgot-password',
    resetPassword: '/auth/reset-password',
    changePassword: '/auth/change-password',
  },
  users: {
    root: '/users',
    me: '/users/me',
  },
  /**
   * The employee portal.
   *
   * One root, and every path built from it. No path in this group takes an
   * employee id: the server resolves the employee from the session, so there is
   * nothing for the client to supply and nothing for it to get wrong.
   */
  me: {
    root: '/me',
  },
  /**
   * The manager's team.
   *
   * One root, like `/me`, and for the same reason: no path in this group takes
   * a manager id. The server derives the team from the signed-in user's
   * reporting line, so there is nothing for the client to supply.
   */
  manager: {
    root: '/manager',
  },
  /**
   * Resignation and offboarding.
   *
   * Only the HR and administrative routes live here. The employee's own
   * separation is under `me` and the manager's team is under `manager`, for
   * the same reason those roots exist at all: neither takes an id, so neither
   * can be pointed at somebody else.
   */
  offboarding: {
    root: '/offboarding',
    summary: '/offboarding/summary',
    resignations: '/offboarding/resignations',
    cases: '/offboarding/cases',
    exitInterviews: '/offboarding/exit-interviews',
  },
  /**
   * HR-facing screens. One root, like the others in this group: the HR
   * endpoints are organization-wide reads, and which employee they answer for
   * is a path segment the server checks against the caller's scope.
   */
  hr: {
    root: '/hr',
  },
  /**
   * The asset register.
   *
   * Only the administrative routes live here. An employee's own assets are
   * under `me`, a manager's team under `manager`, and HR's clearance view under
   * `hr` -- the same split the server makes, for the same reason.
   */
  assets: {
    root: '/assets',
    dashboard: '/assets/dashboard',
    categories: '/assets/categories',
    maintenance: '/assets/maintenance',
  },
  /**
   * The helpdesk.
   *
   * Only the agent-facing routes live here. An employee's own requests are
   * under `me`, and that split is not cosmetic: the `/me` read model cannot
   * carry an internal agent note, and this one can.
   */
  helpdesk: {
    root: '/helpdesk',
    dashboard: '/helpdesk/dashboard',
    categories: '/helpdesk/categories',
  },
  /**
   * Payroll.
   *
   * Only the administrative routes live here. An employee's own compensation
   * is under `me`, for the same reason every other portal path is: no path in
   * that group takes an employee id, so none can be pointed at somebody else.
   */
  payroll: {
    root: '/payroll',
    structures: '/payroll/structures',
    components: '/payroll/components',
    compensation: '/payroll/compensation',
    config: '/payroll/config',
    configHistory: '/payroll/config/history',
    periods: '/payroll/periods',
    leaveRules: '/payroll/rules/leave',
    employeeSettings: '/payroll/employee-settings',
    inputs: '/payroll/inputs',
    runs: '/payroll/runs',
  },
  /**
   * Announcements.
   *
   * Writing and sending them. What an employee actually reads is under `me`,
   * filtered to published notices addressed to them.
   */
  announcements: {
    root: '/announcements',
  },
  employees: {
    root: '/employees',
    dashboard: '/employees/dashboard',
    export: '/employees/export',
  },
  documents: {
    root: '/documents',
    dashboard: '/documents/dashboard',
    categories: '/document-categories',
    types: '/document-types',
  },
  requisitions: {
    root: '/requisitions',
    dashboard: '/requisitions/dashboard',
    export: '/requisitions/export',
  },
  recruitment: {
    root: '/recruitment',
    dashboard: '/recruitment/dashboard',
  },
  interviews: {
    root: '/interviews',
    dashboard: '/interviews/dashboard',
  },
  organization: {
    /**
     * Master paths are `${root}/${slug}` where the slug is the master's
     * `MasterSlug`, so they are built at call time rather than listed here.
     */
    root: '',
    primaryOrganization: '/organizations/primary',
  },
} as const;

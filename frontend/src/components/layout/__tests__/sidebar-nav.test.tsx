import { render, screen } from '@testing-library/react';

import { SidebarNav } from '@/components/layout/sidebar-nav';

let pathname = '/dashboard';

/**
 * Permissions the mocked session holds. `null` means "everything", which is
 * what these tests want by default -- they are about active-state logic, and a
 * session that could not see the items would test nothing.
 */
let held: Set<string> | null = null;

jest.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

jest.mock('@/components/providers/auth-provider', () => ({
  useAuth: () => ({
    can: (permission: string) => held === null || held.has(permission),
  }),
}));

function renderNav(path: string, permissions: string[] | null = null) {
  pathname = path;
  held = permissions === null ? null : new Set(permissions);
  return render(<SidebarNav />);
}

function currentLabels(): string[] {
  return screen
    .getAllByRole('link')
    .filter((link) => link.getAttribute('aria-current') === 'page')
    .map((link) => link.textContent?.trim() ?? '');
}

describe('SidebarNav', () => {
  it('marks exactly one item as current on a master route', () => {
    /* `/organization` is a prefix of every master route, so prefix matching
       alone lights up both the section landing page and the master. */
    renderNav('/organization/grades');

    const current = currentLabels();
    expect(current).toHaveLength(1);
    expect(current[0]).toContain('Grades');
  });

  it('marks the section landing page as current on its own route', () => {
    renderNav('/organization');

    const current = currentLabels();
    expect(current).toHaveLength(1);
    expect(current[0]).toContain('Overview');
  });

  it('keeps a parent lit on a descendant route that is not a section landing page', () => {
    renderNav('/organization/grades/50fe82ac-591c-4afc-9390-d244f8665cba');

    const current = currentLabels();
    expect(current).toHaveLength(1);
    expect(current[0]).toContain('Grades');
  });

  it('has no unreleased modules left in the sidebar', () => {
    // Every "Soon" badge shipped or was removed: Performance became a real
    // page, the org-wide Offboarding row was a stale duplicate of three live
    // role-scoped entries, and System Health was cut as unnecessary. If this
    // fails, a new placeholder crept in -- decide whether it deserves to.
    renderNav('/dashboard');

    expect(screen.queryAllByTitle('Available in a future release')).toHaveLength(0);
  });

  it('renders the Organization section', () => {
    renderNav('/dashboard');

    expect(screen.getByRole('link', { name: /business units/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /employment types/i })).toBeInTheDocument();
  });

  describe('permission filtering', () => {
    it('hides an item the session cannot open', () => {
      renderNav('/dashboard', ['employees:view']);

      expect(screen.queryByRole('link', { name: /Roles & Permissions/ })).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Employees/ })).toBeInTheDocument();
    });

    it('drops a section heading when every item in it is hidden', () => {
      /* A lone "Recruitment" label above nothing reads as a broken page. */
      renderNav('/dashboard', ['employees:view']);

      expect(screen.queryByText('Recruitment')).not.toBeInTheDocument();
    });

    it('keeps items that need no permission', () => {
      renderNav('/dashboard', []);

      // Exact names, not substrings: the employee portal added "My Dashboard"
      // and "My Profile" alongside "Dashboard" and "My Account", and a loose
      // regex would match two links and fail for a reason that has nothing to
      // do with permissions.
      expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'My Account' })).toBeInTheDocument();
    });

    it('keeps the whole employee portal, which needs no permission', () => {
      /* Every one of these is about the caller themselves, so a session with no
         permissions at all must still be able to reach all of them. */
      renderNav('/dashboard', []);

      for (const label of [
        'My Dashboard',
        'My Attendance',
        'My Leave',
        'My Timesheets',
        'My Documents',
        'My Projects',
        'My Holidays',
        'My Profile',
      ]) {
        expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
      }
    });

    it('shows no team screen to a session with only the plain view permissions', () => {
      /* The widening the manager guards were chosen to prevent. Every one of
         these is a permission the base Employee role holds, and none of them
         should put a team screen in the sidebar. */
      renderNav('/dashboard', [
        'attendance:view',
        'leave:view',
        'timesheets:view',
        'performance:view',
        'documents:view',
      ]);

      expect(screen.queryByText('My Team')).not.toBeInTheDocument();
      for (const label of ['Team Dashboard', 'Team Members', 'Team Attendance', 'Team Leave']) {
        expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument();
      }
    });

    it('shows the manager section to a session that approves for its team', () => {
      renderNav('/dashboard', [
        'employees:view',
        'attendance:approve',
        'leave:approve',
        'timesheets:approve',
        'projects:view',
        'performance:create',
      ]);

      for (const label of [
        'Team Dashboard',
        'Team Members',
        'Team Attendance',
        'Team Corrections',
        'Team Leave',
        'Team Timesheets',
        'Team Projects',
        'Team Performance',
        'Team Calendar',
      ]) {
        expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
      }

      // `documents:view` is not held, so the completion screen stays hidden.
      expect(screen.queryByRole('link', { name: 'Team Documents' })).not.toBeInTheDocument();
    });

    it('needs both grants before offering team document completion', () => {
      /* On its own, `documents:view` is a permission every employee holds. */
      renderNav('/dashboard', ['documents:view']);
      expect(screen.queryByRole('link', { name: 'Team Documents' })).not.toBeInTheDocument();

      renderNav('/dashboard', ['documents:view', 'employees:view']);
      expect(screen.getByRole('link', { name: 'Team Documents' })).toBeInTheDocument();
    });
  });

  describe('active state across the team screens', () => {
    it('keeps the team list lit on a member profile', () => {
      renderNav('/manager/team/50fe82ac-591c-4afc-9390-d244f8665cba');

      const current = currentLabels();
      expect(current).toHaveLength(1);
      expect(current[0]).toContain('Team Members');
    });

    it('does not light team attendance on the corrections route', () => {
      /* `/manager/attendance` is a prefix of `/manager/attendance/regularization`. */
      renderNav('/manager/attendance/regularization');

      const current = currentLabels();
      expect(current).toHaveLength(1);
      expect(current[0]).toContain('Team Corrections');
    });
  });
});

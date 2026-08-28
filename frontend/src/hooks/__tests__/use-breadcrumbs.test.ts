import { renderHook } from '@testing-library/react';

import { useBreadcrumbs } from '@/hooks/use-breadcrumbs';

let pathname = '/dashboard';

jest.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

function crumbsFor(path: string) {
  pathname = path;
  return renderHook(() => useBreadcrumbs()).result.current;
}

describe('useBreadcrumbs', () => {
  it('labels known routes from the navigation config', () => {
    const crumbs = crumbsFor('/organization/business-units');
    expect(crumbs.map((c) => c.label)).toEqual(['Organization', 'Business Units']);
  });

  it('marks only the last crumb as current', () => {
    const crumbs = crumbsFor('/organization/grades');
    expect(crumbs.filter((c) => c.isCurrent)).toHaveLength(1);
    expect(crumbs.at(-1)?.isCurrent).toBe(true);
  });

  it('replaces a record id with a readable label', () => {
    // Humanising a UUID produces "50fe82ac 591c 4afc 9390 D244f8665cba",
    // which is worse than useless in a breadcrumb.
    const crumbs = crumbsFor('/organization/grades/50fe82ac-591c-4afc-9390-d244f8665cba');

    expect(crumbs.map((c) => c.label)).toEqual(['Organization', 'Grades', 'Details']);
    expect(crumbs.some((c) => /[0-9a-f]{8}[ -][0-9a-f]{4}/i.test(c.label))).toBe(false);
  });

  it('keeps readable segments alongside a record id', () => {
    const crumbs = crumbsFor('/organization/grades/50fe82ac-591c-4afc-9390-d244f8665cba/edit');
    expect(crumbs.map((c) => c.label)).toEqual(['Organization', 'Grades', 'Details', 'Edit']);
  });

  it('builds cumulative hrefs', () => {
    const crumbs = crumbsFor('/organization/grades');
    expect(crumbs.map((c) => c.href)).toEqual(['/organization', '/organization/grades']);
  });

  it('falls back to the dashboard at the root', () => {
    expect(crumbsFor('/')).toEqual([{ label: 'Dashboard', href: '/dashboard', isCurrent: true }]);
  });
});

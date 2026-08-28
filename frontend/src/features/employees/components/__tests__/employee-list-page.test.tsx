import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EmployeeListPage } from '@/features/employees/components/employee-list-page';
import type { EmployeeRecord } from '@/features/employees/types/employee.types';
import type { Page } from '@/lib/api/types';
import { AppError } from '@/lib/errors';

// ---------------------------------------------------------------------------
// Test doubles
// ---------------------------------------------------------------------------
const replace = jest.fn();
const push = jest.fn();
let searchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push, refresh: jest.fn() }),
  useSearchParams: () => searchParams,
  usePathname: () => '/employees',
}));

const listResult = {
  data: undefined as Page<EmployeeRecord> | undefined,
  error: null as AppError | null,
  isPending: false,
  isFetching: false,
  refetch: jest.fn(),
};

const simpleActions: Record<string, jest.Mock> = {
  activate: jest.fn(),
  deactivate: jest.fn(),
  archive: jest.fn(),
  restore: jest.fn(),
};

const exportMutate = jest.fn();

const capturedQueries: unknown[] = [];

jest.mock('@/features/employees/hooks/use-employees', () => ({
  useEmployeeList: (query: unknown) => {
    capturedQueries.push(query);
    return listResult;
  },
  useSimpleAction: (action: string) => ({ mutate: simpleActions[action], isPending: false }),
  useExportEmployees: () => ({ mutate: exportMutate, isPending: false }),
}));

jest.mock('@/features/organization/hooks/use-masters', () => ({
  useMasterOptions: () => ({ data: { items: [] }, isPending: false }),
}));

function employee(overrides: Partial<EmployeeRecord> = {}): EmployeeRecord {
  return {
    id: 'e1',
    employee_code: 'EMP-000001',
    first_name: 'Priya',
    last_name: 'Sharma',
    full_name: 'Priya Sharma',
    gender: null,
    date_of_birth: null,
    blood_group: null,
    marital_status: null,
    nationality: null,
    personal_email: null,
    mobile_number: null,
    alternate_number: null,
    emergency_contact_name: null,
    emergency_contact_number: null,
    emergency_contact_relationship: null,
    photo_url: null,
    official_email: 'priya@jsan.example',
    official_mobile: null,
    extension_number: null,
    work_mode: null,
    joining_date: '2026-01-15',
    confirmation_date: null,
    employment_status: 'probation',
    employment_type_id: null,
    business_unit_id: null,
    team_id: null,
    designation_id: null,
    grade_id: null,
    work_location_id: null,
    salary_grade_id: null,
    reporting_manager_id: null,
    organization: {
      business_unit: null,
      team: null,
      designation: null,
      grade: null,
      salary_grade: null,
      work_location: null,
      employment_type: null,
    },
    reporting_manager: null,
    user: null,
    ctc: null,
    notes: null,
    addresses: [],
    bank_detail: null,
    identification: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: null,
    updated_by: null,
    deleted_at: null,
    ...overrides,
  };
}

function pageOf(items: EmployeeRecord[]): Page<EmployeeRecord> {
  return {
    items,
    meta: {
      page: 1,
      page_size: 20,
      total_items: items.length,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EmployeeListPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  searchParams = new URLSearchParams();
  capturedQueries.length = 0;
  listResult.data = pageOf([employee()]);
  listResult.error = null;
  listResult.isPending = false;
});

// ---------------------------------------------------------------------------
describe('EmployeeListPage', () => {
  it('lists employees with their identifiers', () => {
    renderPage();

    expect(screen.getByText('Priya Sharma')).toBeInTheDocument();
    expect(screen.getByText('EMP-000001')).toBeInTheDocument();
  });

  it('shows the lifecycle status rather than a generic active/inactive', () => {
    renderPage();
    expect(screen.getByText('Probation')).toBeInTheDocument();
  });

  it('marks an archived employee as archived', () => {
    listResult.data = pageOf([employee({ deleted_at: '2026-02-01T00:00:00Z' })]);
    renderPage();

    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.queryByText('Probation')).not.toBeInTheDocument();
  });

  it('offers an empty state that explains the absence', () => {
    listResult.data = pageOf([]);
    renderPage();

    expect(screen.getByRole('heading', { name: 'No employees yet' })).toBeInTheDocument();
  });

  it('distinguishes "no results" from "nothing exists"', () => {
    searchParams = new URLSearchParams('q=nobody');
    listResult.data = pageOf([]);
    renderPage();

    expect(screen.getByRole('heading', { name: 'No employees match your filters' })).toBeInTheDocument();
  });

  it('exports the current filters rather than the current page', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /export as csv/i }));

    await waitFor(() => {
      expect(exportMutate).toHaveBeenCalledWith(
        expect.objectContaining({ format: 'csv', query: expect.anything() }),
      );
    });
  });

  it('offers both export formats', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: /export/i }));

    expect(await screen.findByRole('menuitem', { name: /export as csv/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /export as excel/i })).toBeInTheDocument();
  });

  it('surfaces a list error instead of an empty table', () => {
    listResult.data = undefined;
    listResult.error = new AppError('The server is unavailable.', { status: 503 });
    renderPage();

    expect(screen.getByRole('alert')).toHaveTextContent('The server is unavailable.');
  });

  it('reads the status filter out of the URL, so a filtered view can be shared', () => {
    searchParams = new URLSearchParams('status=notice_period');
    renderPage();

    expect(capturedQueries.at(-1)).toMatchObject({ employment_status: 'notice_period' });
  });

  it('reads the advanced filters out of the URL too', () => {
    searchParams = new URLSearchParams('team=team-1&location=loc-1');
    renderPage();

    expect(capturedQueries.at(-1)).toMatchObject({
      team_id: 'team-1',
      work_location_id: 'loc-1',
    });
  });

  it('sends no filter key at all when nothing is selected', () => {
    /* An empty string reaches the server as a real value and fails validation. */
    renderPage();

    expect(capturedQueries.at(-1)).not.toHaveProperty('employment_status');
    expect(capturedQueries.at(-1)).not.toHaveProperty('department_id');
  });
});

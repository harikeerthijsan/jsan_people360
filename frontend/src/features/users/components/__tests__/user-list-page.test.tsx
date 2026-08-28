import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UserListPage } from '@/features/users/components/user-list-page';
import type { Page } from '@/lib/api/types';
import { AppError } from '@/lib/errors';
import type { UserRecord } from '@/types/user';

// ---------------------------------------------------------------------------
// Test doubles
// ---------------------------------------------------------------------------
const replace = jest.fn();
const push = jest.fn();
let searchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push, refresh: jest.fn() }),
  useSearchParams: () => searchParams,
  usePathname: () => '/users',
}));

const CURRENT_USER_ID = '11111111-1111-1111-1111-111111111111';

jest.mock('@/components/providers/auth-provider', () => ({
  useAuth: () => ({ user: { id: CURRENT_USER_ID }, status: 'authenticated', isAuthenticated: true }),
}));

const listResult = {
  data: undefined as Page<UserRecord> | undefined,
  error: null as AppError | null,
  isPending: false,
  isFetching: false,
  refetch: jest.fn(),
};

const mutations: Record<string, jest.Mock> = {
  activate: jest.fn(),
  deactivate: jest.fn(),
  archive: jest.fn(),
  restore: jest.fn(),
};

jest.mock('@/features/users/hooks/use-users', () => ({
  useUserList: () => listResult,
  useUserLifecycleAction: (action: string) => ({
    mutate: mutations[action],
    isPending: false,
  }),
}));

function user(overrides: Partial<UserRecord> = {}): UserRecord {
  return {
    id: '22222222-2222-2222-2222-222222222222',
    user_code: 'USR-000002',
    username: 'jane.doe',
    first_name: 'Jane',
    last_name: 'Doe',
    full_name: 'Jane Doe',
    email: 'jane.doe@example.com',
    personal_email: null,
    phone_number: null,
    avatar_url: null,
    gender: null,
    date_of_birth: null,
    business_unit_id: null,
    team_id: null,
    designation_id: null,
    grade_id: null,
    location_id: null,
    employment_type_id: null,
    joining_date: null,
    organization: {
      business_unit: null,
      team: null,
      designation: null,
      grade: null,
      location: null,
      employment_type: null,
    },
    is_active: true,
    status: 'active',
    is_superuser: false,
    force_password_change: false,
    is_locked: false,
    last_login_at: null,
    password_changed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: null,
    updated_by: null,
    deleted_at: null,
    ...overrides,
  };
}

function pageOf(items: UserRecord[]): Page<UserRecord> {
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
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <UserListPage />
    </QueryClientProvider>,
  );
}

describe('UserListPage', () => {
  beforeEach(() => {
    searchParams = new URLSearchParams();
    replace.mockReset();
    push.mockReset();
    for (const mock of Object.values(mutations)) mock.mockReset();
    listResult.data = pageOf([user()]);
    listResult.error = null;
    listResult.isPending = false;
  });

  it('renders the directory columns', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('USR-000002')).toBeInTheDocument();
    expect(screen.getByText('jane.doe')).toBeInTheDocument();
  });

  it('shows "Never" when a user has not signed in', () => {
    renderPage();
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('shows the loading state instead of an empty table', () => {
    listResult.isPending = true;
    listResult.data = undefined;
    renderPage();

    expect(screen.getByText('Loading table data')).toBeInTheDocument();
  });

  it('shows the error state and hides the rows', () => {
    listResult.error = new AppError('The server is unavailable.', { status: 503 });
    listResult.data = undefined;
    renderPage();

    expect(screen.getByRole('alert')).toHaveTextContent('The server is unavailable.');
  });

  it('offers to create the first user when the list is empty', () => {
    listResult.data = pageOf([]);
    renderPage();

    expect(screen.getByRole('heading', { name: /no users yet/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create a user/i })).toBeInTheDocument();
  });

  it('offers to clear filters when a filtered list is empty', () => {
    searchParams = new URLSearchParams('q=nobody');
    listResult.data = pageOf([]);
    renderPage();

    expect(screen.getByRole('heading', { name: /no users match your filters/i })).toBeInTheDocument();
  });

  it('writes the search term to the URL', async () => {
    renderPage();

    await userEvent.type(screen.getByRole('searchbox'), 'jane');

    await waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });
    expect(replace.mock.calls.at(-1)?.[0] as string).toContain('q=jane');
  });

  it('deactivates an active user from the actions menu', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for jane doe/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /deactivate/i }));

    expect(mutations['deactivate']).toHaveBeenCalledWith('22222222-2222-2222-2222-222222222222');
  });

  it('offers activate instead of deactivate for an inactive user', async () => {
    listResult.data = pageOf([user({ is_active: false, status: 'inactive' })]);
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for jane doe/i }));

    expect(await screen.findByRole('menuitem', { name: /activate/i })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /deactivate/i })).not.toBeInTheDocument();
  });

  it('offers only restore for an archived user', async () => {
    listResult.data = pageOf([user({ deleted_at: '2026-02-01T00:00:00Z' })]);
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for jane doe/i }));

    expect(await screen.findByRole('menuitem', { name: /restore/i })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /^archive$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /edit/i })).not.toBeInTheDocument();
  });

  it('disables the self-destructive actions on your own row', async () => {
    /* The API refuses both; disabling here explains why before the click. */
    listResult.data = pageOf([user({ id: CURRENT_USER_ID })]);
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for jane doe/i }));

    expect(await screen.findByRole('menuitem', { name: /deactivate/i })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('menuitem', { name: /archive/i })).toHaveAttribute('aria-disabled', 'true');
  });

  it('asks for confirmation before archiving', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for jane doe/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /archive/i }));

    expect(await screen.findByRole('dialog')).toHaveTextContent(/archive this user/i);
    expect(mutations['archive']).not.toHaveBeenCalled();
  });
});

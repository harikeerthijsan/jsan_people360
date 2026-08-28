import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MasterListPage } from '@/features/organization/components/master-list-page';
import type { MasterRecord } from '@/features/organization/types/organization.types';
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
  usePathname: () => '/organization/business-units',
}));

const listResult = {
  data: undefined as Page<MasterRecord> | undefined,
  error: null as AppError | null,
  isPending: false,
  isFetching: false,
  refetch: jest.fn(),
};

const archiveMutate = jest.fn();
const restoreMutate = jest.fn();

jest.mock('@/features/organization/hooks/use-masters', () => ({
  useMasterList: () => listResult,
  useArchiveMaster: () => ({ mutate: archiveMutate, isPending: false }),
  useRestoreMaster: () => ({ mutate: restoreMutate, isPending: false }),
}));

function record(overrides: Partial<MasterRecord> = {}): MasterRecord {
  return {
    id: '0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f',
    name: 'Technology Services',
    code: 'TECH',
    description: 'Delivery organisation',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: null,
    updated_by: null,
    deleted_at: null,
    ...overrides,
  };
}

function pageOf(items: MasterRecord[]): Page<MasterRecord> {
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
      <MasterListPage slug="business-units" />
    </QueryClientProvider>,
  );
}

describe('MasterListPage', () => {
  beforeEach(() => {
    searchParams = new URLSearchParams();
    replace.mockReset();
    push.mockReset();
    archiveMutate.mockReset();
    restoreMutate.mockReset();
    listResult.data = pageOf([record()]);
    listResult.error = null;
    listResult.isPending = false;
  });

  it('renders the master title and blurb from the registry', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Business units' })).toBeInTheDocument();
    expect(screen.getByText(/top level of the organizational hierarchy/i)).toBeInTheDocument();
  });

  it('renders the configured columns', () => {
    renderPage();

    expect(screen.getByRole('columnheader', { name: /name/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /code/i })).toBeInTheDocument();
    expect(screen.getByText('Technology Services')).toBeInTheDocument();
    expect(screen.getByText('TECH')).toBeInTheDocument();
  });

  it('shows the record status', () => {
    renderPage();
    expect(screen.getByText('Active')).toBeInTheDocument();
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

  it('offers to create the first record when the list is empty and unfiltered', () => {
    listResult.data = pageOf([]);
    renderPage();

    expect(screen.getByRole('heading', { name: /no business units yet/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create the first business unit/i })).toBeInTheDocument();
  });

  it('offers to clear filters when a filtered list is empty', () => {
    /* Telling a user to "create the first record" when they have simply
       mistyped a search term is actively unhelpful. */
    searchParams = new URLSearchParams('q=nothing');
    listResult.data = pageOf([]);
    renderPage();

    expect(
      screen.getByRole('heading', { name: /no business units match your filters/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
  });

  it('writes the search term to the URL', async () => {
    renderPage();

    await userEvent.type(screen.getByRole('searchbox'), 'cloud');

    await waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });
    const target = replace.mock.calls.at(-1)?.[0] as string;
    expect(target).toContain('q=cloud');
  });

  it('writes the sort selection to the URL', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /code/i }));

    const target = replace.mock.calls.at(-1)?.[0] as string;
    expect(target).toContain('sort=code');
  });

  it('resets to page one when the filter changes', async () => {
    searchParams = new URLSearchParams('page=3');
    renderPage();

    await userEvent.type(screen.getByRole('searchbox'), 'x');

    await waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });
    const target = replace.mock.calls.at(-1)?.[0] as string;
    expect(target).not.toContain('page=3');
  });

  it('asks for confirmation before archiving', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for technology services/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /archive/i }));

    expect(await screen.findByRole('dialog')).toHaveTextContent(/archive this business unit/i);
    // Nothing is archived until the dialog is confirmed.
    expect(archiveMutate).not.toHaveBeenCalled();
  });

  it('archives once the dialog is confirmed', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for technology services/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /archive/i }));
    await userEvent.click(await screen.findByRole('button', { name: /^archive$/i }));

    expect(archiveMutate).toHaveBeenCalledWith('0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f', expect.anything());
  });

  it('offers restore instead of archive for an archived record', async () => {
    listResult.data = pageOf([record({ deleted_at: '2026-02-01T00:00:00Z' })]);
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /actions for technology services/i }));

    expect(await screen.findByRole('menuitem', { name: /restore/i })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /archive/i })).not.toBeInTheDocument();
  });
});

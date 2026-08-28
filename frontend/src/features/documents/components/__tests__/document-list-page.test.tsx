import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DocumentListPage } from '@/features/documents/components/document-list-page';
import type { DocumentRecord } from '@/features/documents/types/document.types';
import type { Page } from '@/lib/api/types';
import type { AppError } from '@/lib/errors';

/**
 * The filter panel's URL contract.
 *
 * Two of these filters are *dependent*: choosing a category invalidates the
 * chosen type, and choosing an owner type invalidates the chosen owner. Both
 * therefore change two query parameters at once, which is where a
 * one-parameter-at-a-time setter silently loses the first change — each call
 * rebuilds the URL from the same snapshot, so the second overwrites the first.
 * These tests pin the resulting URL rather than the mechanism.
 */

const replace = jest.fn();
let searchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: jest.fn(), refresh: jest.fn() }),
  useSearchParams: () => searchParams,
  usePathname: () => '/documents',
}));

const listResult = {
  data: undefined as Page<DocumentRecord> | undefined,
  error: null as AppError | null,
  isPending: false,
  isFetching: false,
  refetch: jest.fn(),
};

jest.mock('@/features/documents/hooks/use-documents', () => ({
  useDocumentList: () => listResult,
  useDocumentCategories: () => ({
    data: { items: [{ id: 'cat-1', name: 'Identity Documents', code: 'IDENTITY' }] },
    isPending: false,
  }),
  useDocumentTypes: () => ({ data: { items: [] }, isPending: false }),
  useDocumentAction: () => ({ mutate: jest.fn(), isPending: false }),
  useDownloadDocument: () => ({ mutate: jest.fn(), isPending: false }),
}));

jest.mock('@/features/documents/hooks/use-owner-options', () => ({
  useOwnerOptions: (ownerType: string | undefined) => ({
    options: ownerType === 'candidate' ? [{ value: 'can-1', label: 'Meera Nair', hint: 'CAN-000001' }] : [],
    isLoading: false,
    emptyMessage: 'Choose what kind of owner first',
  }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DocumentListPage />
    </QueryClientProvider>,
  );
}

/** The last URL the page asked the router to replace with. */
function lastUrl(): URLSearchParams {
  const call = replace.mock.calls.at(-1);
  return new URLSearchParams(String(call?.[0] ?? '').replace(/^\?/, ''));
}

beforeEach(() => {
  searchParams = new URLSearchParams();
  listResult.data = {
    items: [],
    meta: {
      page: 1,
      page_size: 20,
      total_items: 0,
      total_pages: 0,
      has_next: false,
      has_previous: false,
    },
  };
  replace.mockClear();
});

describe('DocumentListPage filters', () => {
  it('keeps the owner type when it clears the owner alongside it', async () => {
    const user = userEvent.setup();
    // An owner is already chosen, so switching type has something to clear.
    searchParams = new URLSearchParams('owner_type=employee&owner_id=emp-1');
    renderPage();

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    await user.click(screen.getByRole('combobox', { name: /owner type/i }));
    await user.click(await screen.findByRole('option', { name: 'Candidate' }));

    await waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });

    const params = lastUrl();
    expect(params.get('owner_type')).toBe('candidate');
    expect(params.get('owner_id')).toBeNull();
  });

  it('keeps the category when it clears the document type alongside it', async () => {
    const user = userEvent.setup();
    searchParams = new URLSearchParams('type=type-9');
    renderPage();

    await user.click(screen.getByRole('button', { name: 'Filters' }));
    await user.click(screen.getByRole('combobox', { name: /^category$/i }));
    await user.click(await screen.findByRole('option', { name: 'Identity Documents' }));

    await waitFor(() => {
      expect(replace).toHaveBeenCalled();
    });

    const params = lastUrl();
    expect(params.get('category')).toBe('cat-1');
    expect(params.get('type')).toBeNull();
  });

  it('offers only the statuses a document can actually hold', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('combobox', { name: /filter by status/i }));

    expect(await screen.findByRole('option', { name: 'Approved' })).toBeInTheDocument();
    // Expiry is derived and archiving uses its own view, so neither is a status
    // any document is ever stored with.
    expect(screen.queryByRole('option', { name: 'Expired' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Archived' })).not.toBeInTheDocument();
  });
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Pagination, type PageMeta } from '@/components/common/pagination';

function meta(overrides: Partial<PageMeta> = {}): PageMeta {
  return {
    page: 2,
    page_size: 20,
    total_items: 57,
    total_pages: 3,
    has_next: true,
    has_previous: true,
    ...overrides,
  };
}

describe('Pagination', () => {
  it('renders nothing when there are no results', () => {
    const { container } = render(
      <Pagination
        meta={meta({ total_items: 0, total_pages: 0, has_next: false, has_previous: false })}
        onPageChange={jest.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('summarises the visible range', () => {
    render(<Pagination meta={meta()} onPageChange={jest.fn()} itemLabel="practices" />);

    const summary = screen.getByText(/showing/i);
    expect(summary).toHaveTextContent('21');
    expect(summary).toHaveTextContent('40');
    expect(summary).toHaveTextContent('57');
    expect(summary).toHaveTextContent('practices');
  });

  it('caps the range at the total on the final page', () => {
    render(<Pagination meta={meta({ page: 3, has_next: false })} onPageChange={jest.fn()} />);

    // Page 3 of 20-per-page over 57 items ends at 57, not 60.
    expect(screen.getByText(/showing/i)).toHaveTextContent('57');
  });

  it('moves to the next page', async () => {
    const onPageChange = jest.fn();
    render(<Pagination meta={meta()} onPageChange={onPageChange} />);

    await userEvent.click(screen.getByRole('button', { name: /next/i }));

    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it('moves to the previous page', async () => {
    const onPageChange = jest.fn();
    render(<Pagination meta={meta()} onPageChange={onPageChange} />);

    await userEvent.click(screen.getByRole('button', { name: /previous/i }));

    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it('disables the controls at each end of the range', () => {
    render(
      <Pagination meta={meta({ page: 1, has_previous: false, has_next: true })} onPageChange={jest.fn()} />,
    );

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();
  });
});

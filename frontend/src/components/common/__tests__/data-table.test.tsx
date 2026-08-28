import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createPortal } from 'react-dom';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { AppError } from '@/lib/errors';

interface Row {
  id: string;
  name: string;
  department: string;
}

const rows: Row[] = [
  { id: '1', name: 'Jane Doe', department: 'Engineering' },
  { id: '2', name: 'Ravi Kumar', department: 'People Operations' },
];

const columns: DataTableColumn<Row>[] = [
  { id: 'name', header: 'Name', cell: (row) => row.name },
  { id: 'department', header: 'Department', cell: (row) => row.department },
];

function renderTable(overrides: Partial<React.ComponentProps<typeof DataTable<Row>>> = {}) {
  return render(<DataTable columns={columns} rows={rows} getRowId={(row) => row.id} {...overrides} />);
}

describe('DataTable', () => {
  it('renders headers and rows', () => {
    renderTable();

    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('People Operations')).toBeInTheDocument();
  });

  it('shows the loading skeleton instead of an empty table while loading', () => {
    renderTable({ isLoading: true });

    expect(screen.getByText('Loading table data')).toBeInTheDocument();
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
  });

  it('shows the empty state when there are no rows', () => {
    renderTable({ rows: [], emptyTitle: 'No employees found' });

    expect(screen.getByRole('heading', { name: 'No employees found' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows the error state, and prefers it over the row data', () => {
    renderTable({ error: new AppError('The server is unavailable.', { status: 503 }) });

    expect(screen.getByRole('alert')).toHaveTextContent('The server is unavailable.');
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
  });

  it('calls onRetry from the error state', async () => {
    const onRetry = jest.fn();
    renderTable({ error: new AppError('Failed'), onRetry });

    await userEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('makes rows interactive only when onRowClick is supplied', async () => {
    const onRowClick = jest.fn();
    const { rerender } = renderTable();

    expect(screen.queryAllByRole('button')).toHaveLength(0);

    rerender(<DataTable columns={columns} rows={rows} getRowId={(row) => row.id} onRowClick={onRowClick} />);

    const [firstRow] = screen.getAllByRole('button');
    expect(firstRow).toBeDefined();
    await userEvent.click(firstRow as HTMLElement);

    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });

  it('activates a row from the keyboard', async () => {
    const onRowClick = jest.fn();
    renderTable({ onRowClick });

    const [firstRow] = screen.getAllByRole('button');
    (firstRow as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');

    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });

  it('ignores a click that came from a portal rendered inside a cell', async () => {
    /**
     * React routes events from a portal through the component tree rather than
     * the DOM tree, so a click on a row action menu -- rendered from a cell but
     * portalled to the body -- arrives at the row's own click handler. Acting
     * on it navigated away and cancelled whatever the menu item had just
     * started, which silently broke every archive confirmation in the product.
     */
    const onRowClick = jest.fn();
    const onAction = jest.fn();

    const withPortal: DataTableColumn<Row>[] = [
      ...columns,
      {
        id: 'actions',
        header: 'Actions',
        cell: () =>
          createPortal(
            <button type="button" onClick={onAction}>
              Archive
            </button>,
            document.body,
          ),
      },
    ];

    render(<DataTable columns={withPortal} rows={rows} getRowId={(row) => row.id} onRowClick={onRowClick} />);

    await userEvent.click(screen.getAllByRole('button', { name: 'Archive' })[0] as HTMLElement);

    expect(onAction).toHaveBeenCalled();
    expect(onRowClick).not.toHaveBeenCalled();
  });
});

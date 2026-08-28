import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EmptyState } from '@/components/common/empty-state';

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title="No employees yet" />);
    expect(screen.getByRole('heading', { name: 'No employees yet' })).toBeInTheDocument();
  });

  it('renders the description when supplied', () => {
    render(<EmptyState title="No employees yet" description="Add your first employee to get started." />);
    expect(screen.getByText('Add your first employee to get started.')).toBeInTheDocument();
  });

  it('renders no action button when none is supplied', () => {
    render(<EmptyState title="No employees yet" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('invokes the primary action on click', async () => {
    const onClick = jest.fn();
    render(<EmptyState title="No employees yet" action={{ label: 'Add employee', onClick }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Add employee' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders both actions when supplied', () => {
    render(
      <EmptyState
        title="No employees yet"
        action={{ label: 'Add employee', onClick: jest.fn() }}
        secondaryAction={{ label: 'Import CSV', onClick: jest.fn() }}
      />,
    );

    expect(screen.getByRole('button', { name: 'Add employee' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import CSV' })).toBeInTheDocument();
  });
});

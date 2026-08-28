import { render, screen } from '@testing-library/react';

import { StatusBadge } from '@/components/common/status-badge';

describe('StatusBadge', () => {
  it('renders an active record', () => {
    render(<StatusBadge status="active" />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders an inactive record', () => {
    render(<StatusBadge status="inactive" />);
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('shows archived in place of the business status', () => {
    // Archived and inactive are different states; the badge must not conflate them.
    render(<StatusBadge status="active" archived />);

    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.queryByText('Active')).not.toBeInTheDocument();
  });

  it('shows archived even when the record is inactive', () => {
    render(<StatusBadge status="inactive" archived />);

    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.queryByText('Inactive')).not.toBeInTheDocument();
  });
});

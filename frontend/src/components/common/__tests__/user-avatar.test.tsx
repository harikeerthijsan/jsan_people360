import { render, screen } from '@testing-library/react';

import { UserAvatar, UserIdentity } from '@/components/common/user-avatar';

describe('UserAvatar', () => {
  it('falls back to initials when there is no photo', () => {
    render(<UserAvatar name="Jane Doe" />);
    expect(screen.getByText('JD')).toBeInTheDocument();
  });

  it('handles a single-word name', () => {
    render(<UserAvatar name="Madonna" />);
    expect(screen.getByText('M')).toBeInTheDocument();
  });
});

describe('UserIdentity', () => {
  it('renders the name and the secondary line', () => {
    render(<UserIdentity name="Jane Doe" secondary="jane.doe@example.com" />);

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane.doe@example.com')).toBeInTheDocument();
  });

  it('omits the secondary line when there is nothing to show', () => {
    render(<UserIdentity name="Jane Doe" />);

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.queryByText('jane.doe@example.com')).not.toBeInTheDocument();
  });
});

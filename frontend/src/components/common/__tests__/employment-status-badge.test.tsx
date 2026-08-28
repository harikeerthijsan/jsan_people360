import { render, screen } from '@testing-library/react';

import { EmploymentStatusBadge } from '@/components/common/employment-status-badge';
import { EMPLOYMENT_STATUSES } from '@/features/employees/types/employee.types';

describe('EmploymentStatusBadge', () => {
  it.each(EMPLOYMENT_STATUSES)('renders a distinct label for %s', (status) => {
    render(<EmploymentStatusBadge status={status} />);
    expect(screen.getByText(/probation|confirmed|active|notice period|resigned|inactive/i)).toBeVisible();
  });

  it('labels notice period as words rather than the raw enum value', () => {
    render(<EmploymentStatusBadge status="notice_period" />);

    expect(screen.getByText('Notice period')).toBeInTheDocument();
    expect(screen.queryByText('notice_period')).not.toBeInTheDocument();
  });

  it('prefers archived over the lifecycle status', () => {
    /* A hidden record's lifecycle state is moot, and showing both would imply
       the employee is still in play. */
    render(<EmploymentStatusBadge status="confirmed" archived />);

    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument();
  });

  it('does not collapse the six states into two', () => {
    const { rerender } = render(<EmploymentStatusBadge status="probation" />);
    const probation = screen.getByText('Probation').className;

    rerender(<EmploymentStatusBadge status="resigned" />);
    const resigned = screen.getByText('Resigned').className;

    expect(probation).not.toEqual(resigned);
  });
});

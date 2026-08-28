import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MaskedValue } from '@/components/common/masked-value';

describe('MaskedValue', () => {
  const base = {
    masked: 'XXXXXXXX0123',
    label: 'Aadhaar number',
    isRevealed: false,
    onToggle: jest.fn(),
  };

  it('shows the masked value the server sent', () => {
    render(<MaskedValue {...base} />);
    expect(screen.getByText('XXXXXXXX0123')).toBeInTheDocument();
  });

  it('never derives the mask on the client', () => {
    /* The full value must not be in the DOM until it has been fetched. */
    render(<MaskedValue {...base} revealed="234567890123" isRevealed={false} />);
    expect(screen.queryByText('234567890123')).not.toBeInTheDocument();
  });

  it('shows the full value once revealed', () => {
    render(<MaskedValue {...base} revealed="234567890123" isRevealed />);
    expect(screen.getByText('234567890123')).toBeInTheDocument();
  });

  it('keeps showing the mask while the real value is still in flight', () => {
    render(<MaskedValue {...base} isRevealed revealed={undefined} />);
    expect(screen.getByText('XXXXXXXX0123')).toBeInTheDocument();
  });

  it('renders an em dash when there is nothing to show', () => {
    render(<MaskedValue {...base} masked={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('makes revealing a deliberate action rather than a hover', async () => {
    const onToggle = jest.fn();
    render(<MaskedValue {...base} onToggle={onToggle} />);

    const button = screen.getByRole('button', { name: 'Reveal Aadhaar number' });
    expect(button).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('offers to hide the value once it is showing', () => {
    render(<MaskedValue {...base} revealed="234567890123" isRevealed />);

    const button = screen.getByRole('button', { name: 'Hide Aadhaar number' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('disables the toggle while loading', () => {
    render(<MaskedValue {...base} isLoading />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

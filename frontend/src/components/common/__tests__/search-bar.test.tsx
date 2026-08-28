import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SearchBar } from '@/components/common/search-bar';

describe('SearchBar', () => {
  it('renders the current value', () => {
    render(<SearchBar value="engineering" onChange={jest.fn()} />);
    expect(screen.getByRole('searchbox')).toHaveValue('engineering');
  });

  it('does not report a change on every keystroke', async () => {
    const onChange = jest.fn();
    render(<SearchBar value="" onChange={onChange} debounceMs={50} />);

    await userEvent.type(screen.getByRole('searchbox'), 'cloud');

    // Five characters typed; the callback must not have fired five times.
    expect(onChange).not.toHaveBeenCalledTimes(5);
  });

  it('reports the final value after the debounce', async () => {
    const onChange = jest.fn();
    render(<SearchBar value="" onChange={onChange} debounceMs={50} />);

    await userEvent.type(screen.getByRole('searchbox'), 'cloud');

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('cloud');
    });
  });

  it('shows no clear button when empty', () => {
    render(<SearchBar value="" onChange={jest.fn()} />);
    expect(screen.queryByRole('button', { name: /clear search/i })).not.toBeInTheDocument();
  });

  it('clears immediately when the clear button is used', async () => {
    const onChange = jest.fn();
    render(<SearchBar value="cloud" onChange={onChange} debounceMs={5000} />);

    await userEvent.click(screen.getByRole('button', { name: /clear search/i }));

    // Clearing bypasses the debounce; waiting five seconds to see all the rows
    // again would feel broken.
    expect(onChange).toHaveBeenCalledWith('');
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });

  it('clears on Escape', async () => {
    const onChange = jest.fn();
    render(<SearchBar value="cloud" onChange={onChange} debounceMs={5000} />);

    await userEvent.type(screen.getByRole('searchbox'), '{Escape}');

    expect(onChange).toHaveBeenCalledWith('');
  });

  it('re-syncs when the parent changes the value', () => {
    const { rerender } = render(<SearchBar value="cloud" onChange={jest.fn()} />);
    expect(screen.getByRole('searchbox')).toHaveValue('cloud');

    rerender(<SearchBar value="" onChange={jest.fn()} />);

    expect(screen.getByRole('searchbox')).toHaveValue('');
  });
});

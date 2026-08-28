import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FileUpload } from '@/components/common/file-upload';

describe('FileUpload', () => {
  it('selects a valid file and displays its name', async () => {
    const user = userEvent.setup();
    const onSelect = jest.fn();
    render(<FileUpload onSelect={onSelect} accept=".pdf" />);
    const file = new File(['pdf'], 'passport.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText(/choose a file/i), file);
    expect(onSelect).toHaveBeenCalledWith(file);
    expect(screen.getByText('passport.pdf')).toBeInTheDocument();
  });

  it('announces a rejected dropped file', () => {
    const onSelect = jest.fn();
    const { container } = render(
      <FileUpload onSelect={onSelect} validate={() => ({ message: 'Only PDF files are allowed.' })} />,
    );
    const file = new File(['bad'], 'bad.exe', { type: 'application/octet-stream' });
    fireEvent.drop(container.querySelector('.border-dashed') as Element, {
      dataTransfer: { files: [file] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Only PDF files are allowed.');
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('renders upload progress accessibly', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<FileUpload onSelect={jest.fn()} />);
    await user.upload(screen.getByLabelText(/choose a file/i), new File(['x'], 'file.pdf'));
    rerender(<FileUpload onSelect={jest.fn()} isUploading progress={45} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  });
});

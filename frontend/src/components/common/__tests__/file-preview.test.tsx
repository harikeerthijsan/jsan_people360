import { render, screen } from '@testing-library/react';

import { FilePreviewModal, ImageViewer, PdfViewer } from '@/components/common/file-preview';

describe('document viewers', () => {
  it('renders an image with an accessible description', () => {
    render(<ImageViewer url="blob:image" filename="identity.png" />);
    expect(screen.getByRole('img', { name: 'identity.png' })).toHaveAttribute('src', 'blob:image');
  });

  it('renders a labelled PDF object', () => {
    const { container } = render(<PdfViewer url="blob:pdf" filename="contract.pdf" />);
    expect(container.querySelector('object')).toHaveAttribute('aria-label', 'contract.pdf');
  });

  it('shows loading state while an authenticated preview is fetched', () => {
    render(
      <FilePreviewModal
        open
        onOpenChange={jest.fn()}
        title="Passport"
        filename="passport.pdf"
        contentType="application/pdf"
        url={null}
        isLoading
      />,
    );
    expect(screen.getByText(/loading preview/i)).toBeInTheDocument();
  });
});

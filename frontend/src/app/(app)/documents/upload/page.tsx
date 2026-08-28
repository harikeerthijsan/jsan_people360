import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { DocumentUploadPage } from '@/features/documents/components/document-upload-page';

export const metadata: Metadata = {
  title: 'Upload document',
};

export default function UploadDocumentRoute(): React.JSX.Element {
  return (
    // Reads `?owner_type=` and `?owner_id=` when arriving from another module's
    // document panel, which requires a Suspense boundary.
    <Suspense fallback={<LoadingState message="Loading…" />}>
      <DocumentUploadPage />
    </Suspense>
  );
}

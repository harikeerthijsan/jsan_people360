import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { DocumentListPage } from '@/features/documents/components/document-list-page';

export const metadata: Metadata = {
  title: 'Documents',
  description: 'The shared document vault used by every module.',
};

export default function DocumentsRoute(): React.JSX.Element {
  return (
    // The list reads its filters from the query string, which requires a
    // Suspense boundary under the App Router.
    <Suspense fallback={<LoadingState message="Loading documents…" />}>
      <DocumentListPage />
    </Suspense>
  );
}

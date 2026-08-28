import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { DocumentDetailPage } from '@/features/documents/components/document-detail-page';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function DocumentDetailRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { id } = await params;

  return (
    // The page keeps the active tab in `?tab=`, which requires a Suspense
    // boundary.
    <Suspense fallback={<LoadingState message="Loading document…" />}>
      <DocumentDetailPage documentId={id} />
    </Suspense>
  );
}

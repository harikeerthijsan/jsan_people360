import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { UserDetailPage } from '@/features/users/components/user-detail-page';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function UserDetailRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { id } = await params;

  return (
    // The page reads `?reset=1` to open the password dialog directly from the
    // list, which requires a Suspense boundary.
    <Suspense fallback={<LoadingState message="Loading user…" />}>
      <UserDetailPage userId={id} />
    </Suspense>
  );
}

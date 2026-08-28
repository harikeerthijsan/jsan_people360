import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { UserListPage } from '@/features/users/components/user-list-page';

export const metadata: Metadata = {
  title: 'Users',
  description: 'Manage the people with access to JSAN People360.',
};

export default function UsersRoute(): React.JSX.Element {
  return (
    // The list reads its state from the query string, which requires a
    // Suspense boundary under the App Router.
    <Suspense fallback={<LoadingState message="Loading users…" />}>
      <UserListPage />
    </Suspense>
  );
}

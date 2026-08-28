import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { EmployeeListPage } from '@/features/employees/components/employee-list-page';

export const metadata: Metadata = {
  title: 'Employees',
  description: 'The single source of truth for everyone the organization employs.',
};

export default function EmployeesRoute(): React.JSX.Element {
  return (
    // The list reads its filters from the query string, which requires a
    // Suspense boundary under the App Router.
    <Suspense fallback={<LoadingState message="Loading employees…" />}>
      <EmployeeListPage />
    </Suspense>
  );
}

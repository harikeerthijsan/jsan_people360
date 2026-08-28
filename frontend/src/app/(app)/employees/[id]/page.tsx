import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { EmployeeProfilePage } from '@/features/employees/components/employee-profile-page';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EmployeeProfileRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { id } = await params;

  return (
    // The profile keeps the active tab in `?tab=`, which requires a Suspense
    // boundary.
    <Suspense fallback={<LoadingState message="Loading employee…" />}>
      <EmployeeProfilePage employeeId={id} />
    </Suspense>
  );
}

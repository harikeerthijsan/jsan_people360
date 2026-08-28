import type * as React from 'react';

import { EmployeeEditPage } from '@/features/employees/components/employee-form-page';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditEmployeeRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { id } = await params;

  return <EmployeeEditPage employeeId={id} />;
}

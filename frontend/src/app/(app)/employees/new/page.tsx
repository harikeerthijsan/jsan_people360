import type { Metadata } from 'next';
import type * as React from 'react';

import { EmployeeCreatePage } from '@/features/employees/components/employee-form-page';

export const metadata: Metadata = {
  title: 'New employee',
};

export default function NewEmployeeRoute(): React.JSX.Element {
  return <EmployeeCreatePage />;
}

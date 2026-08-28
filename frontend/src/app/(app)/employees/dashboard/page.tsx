import type { Metadata } from 'next';
import type * as React from 'react';

import { EmployeeDashboardPage } from '@/features/employees/components/employee-dashboard-page';

export const metadata: Metadata = {
  title: 'Employee dashboard',
  description: 'Headcount and composition across the organization.',
};

export default function EmployeeDashboardRoute(): React.JSX.Element {
  return <EmployeeDashboardPage />;
}

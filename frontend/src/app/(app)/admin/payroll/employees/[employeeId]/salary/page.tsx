import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { EmployeeSalaryPage } from '@/features/payroll/components/employee-salary-page';

interface Props {
  params: Promise<{ employeeId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { employeeId } = await params;
  return (
    <RequirePermission anyOf={['payroll:view', 'payroll:team_view']} title="employee compensation">
      <EmployeeSalaryPage employeeId={employeeId} />
    </RequirePermission>
  );
}

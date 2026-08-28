import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollEmployeePayslipPage } from '@/features/payroll/components/payroll-payslips-page';

interface Props {
  params: Promise<{ employeeId: string; payslipId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { employeeId, payslipId } = await params;
  return (
    <RequirePermission anyOf={['payroll:payslip_view', 'payroll:team_view']} title="payslips">
      <PayrollEmployeePayslipPage employeeId={employeeId} payslipId={payslipId} />
    </RequirePermission>
  );
}

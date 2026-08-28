import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollPayslipsPage } from '@/features/payroll/components/payroll-payslips-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:payslip_view" title="payslips">
      <PayrollPayslipsPage />
    </RequirePermission>
  );
}

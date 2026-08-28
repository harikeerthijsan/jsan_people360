import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollEmployeesPage } from '@/features/payroll/components/payroll-employees-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:view" title="the payroll register">
      <PayrollEmployeesPage />
    </RequirePermission>
  );
}

import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollPeriodsPage } from '@/features/payroll/components/payroll-periods-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission anyOf={['payroll:config_view', 'payroll:period_manage']} title="payroll periods">
      <PayrollPeriodsPage />
    </RequirePermission>
  );
}

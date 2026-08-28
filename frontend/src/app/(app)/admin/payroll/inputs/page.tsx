import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollInputsPage } from '@/features/payroll/components/payroll-inputs-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:inputs_view" title="payroll inputs">
      <PayrollInputsPage />
    </RequirePermission>
  );
}

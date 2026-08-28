import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollSettlementsPage } from '@/features/payroll/components/payroll-settlements-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:settlement_view" title="final settlement">
      <PayrollSettlementsPage />
    </RequirePermission>
  );
}

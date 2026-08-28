import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollHistoryPage } from '@/features/payroll/components/payroll-history-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:finalized_view" title="payroll history">
      <PayrollHistoryPage />
    </RequirePermission>
  );
}

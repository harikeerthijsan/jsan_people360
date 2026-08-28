import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollApprovalQueuePage } from '@/features/payroll/components/payroll-approval-queue-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:approval_view" title="payroll approval">
      <PayrollApprovalQueuePage />
    </RequirePermission>
  );
}

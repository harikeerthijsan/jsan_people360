import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollReportsPage } from '@/features/payroll/components/payroll-reports-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:report_view" title="payroll reports">
      <PayrollReportsPage />
    </RequirePermission>
  );
}

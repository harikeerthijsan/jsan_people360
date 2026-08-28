import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollReviewDashboardPage } from '@/features/payroll/components/payroll-review-dashboard-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:review_view" title="payroll review">
      <PayrollReviewDashboardPage />
    </RequirePermission>
  );
}

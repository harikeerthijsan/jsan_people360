import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRunReviewPage } from '@/features/payroll/components/payroll-run-review-page';

interface Props {
  params: Promise<{ runId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { runId } = await params;
  return (
    <RequirePermission permission="payroll:review_view" title="payroll review">
      <PayrollRunReviewPage runId={runId} />
    </RequirePermission>
  );
}

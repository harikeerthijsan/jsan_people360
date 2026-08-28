import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollSettlementDetailPage } from '@/features/payroll/components/payroll-settlement-detail-page';

interface Props {
  params: Promise<{ settlementId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { settlementId } = await params;
  return (
    <RequirePermission permission="payroll:settlement_view" title="final settlement">
      <PayrollSettlementDetailPage settlementId={settlementId} />
    </RequirePermission>
  );
}

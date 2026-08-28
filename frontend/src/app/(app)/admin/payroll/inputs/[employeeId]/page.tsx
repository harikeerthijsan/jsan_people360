import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollInputDetailPage } from '@/features/payroll/components/payroll-input-detail-page';

interface Props {
  params: Promise<{ employeeId: string }>;
  searchParams: Promise<{ period?: string }>;
}

export default async function Page({ params, searchParams }: Props): Promise<React.JSX.Element> {
  const { employeeId } = await params;
  const { period } = await searchParams;
  return (
    <RequirePermission anyOf={['payroll:inputs_view', 'payroll:team_view']} title="payroll inputs">
      <PayrollInputDetailPage employeeId={employeeId} periodId={period ?? ''} />
    </RequirePermission>
  );
}

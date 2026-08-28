'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useEmployeeAssets } from '@/features/assets/hooks';
import { ASSET_CONDITION_LABELS, type EmployeeAssetClearanceRow } from '@/features/assets/types';

/**
 * HR asset view.
 *
 * Sight for a clearance, and nothing else. There is no create, assign, transfer
 * or retire control here because there is no HR endpoint behind one -- §12 of
 * the brief, enforced on the server and merely reflected in this screen.
 *
 * The employee is looked up by id because that is what an HR user has in front
 * of them on an offboarding case. The server checks the id against the caller's
 * scope before reading anything, so this cannot be pointed at somebody outside
 * their reach.
 */

interface Props {
  employeeId?: string;
}

export function HrAssetsPage({ employeeId: initial }: Props): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState(initial ?? '');
  const query = useEmployeeAssets(employeeId);

  const rows = query.data ?? [];
  const outstanding = rows.filter((row) => row.returnable).length;

  const columns: DataTableColumn<EmployeeAssetClearanceRow>[] = [
    {
      id: 'asset',
      header: 'Asset',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">
            {row.asset_code} · {row.category}
          </p>
        </div>
      ),
    },
    { id: 'tag', header: 'Tag', cell: (row) => <span className="tabular-nums">{row.asset_tag}</span> },
    { id: 'assigned', header: 'Assigned', cell: (row) => row.assigned_date },
    {
      id: 'condition',
      header: 'Condition',
      cell: (row) => <Badge variant="outline">{ASSET_CONDITION_LABELS[row.condition]}</Badge>,
    },
    {
      id: 'returnable',
      header: 'Clearance',
      cell: (row) =>
        row.returnable ? <Badge>Expected back</Badge> : <Badge variant="secondary">Not expected back</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employee assets"
        description="What one employee is holding, for onboarding records and exit clearance. Read only — asset administration is IT's."
      />

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-base">Look up an employee</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <EmployeePicker id="employee-id" value={employeeId} onChange={setEmployeeId} />
            <p className="text-muted-foreground text-xs">
              Also reachable from an offboarding case, where the clearance list is seeded from this same
              register.
            </p>
          </div>
        </CardContent>
      </Card>

      {employeeId === '' ? (
        <EmptyState
          title="No employee selected"
          description="Enter an employee ID to see what they are holding."
        />
      ) : (
        <>
          {rows.length > 0 ? (
            <p className="text-muted-foreground text-sm">
              {rows.length} asset{rows.length === 1 ? '' : 's'} issued, {outstanding} expected back at exit.
            </p>
          ) : null}
          <DataTable
            rows={rows}
            columns={columns}
            getRowId={(row) => row.asset_id}
            isLoading={query.isLoading}
            error={query.error}
            emptyTitle="No assets issued"
            emptyDescription="This employee is not currently holding any registered company property."
          />
        </>
      )}
    </div>
  );
}

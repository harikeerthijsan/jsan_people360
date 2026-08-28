'use client';

import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { Textarea } from '@/components/ui/textarea';
import { Can } from '@/components/common/can';
import {
  useAsset,
  useAssignAsset,
  useChangeAssetStatus,
  useReturnAsset,
  useTransferAsset,
} from '@/features/assets/hooks';
import {
  ASSET_CONDITION_LABELS,
  ASSET_STATUS_LABELS,
  WARRANTY_STATE_LABELS,
  type AssetCondition,
  type AssetStatus,
} from '@/features/assets/types';

/**
 * One asset: overview, current custody, and its complete history.
 *
 * The custody controls are wrapped in `Can`, but that is presentation only --
 * the server refuses each of them independently, and a hidden button is not a
 * permission check. What `Can` buys is not showing somebody an action that will
 * fail.
 *
 * The status control offers `allowed_transitions` from the response rather than
 * a list built here. The transition table lives on the server; a copy in the
 * client would be a second one, and the two would disagree the first time
 * either changed.
 */

const CONDITIONS: AssetCondition[] = ['new', 'excellent', 'good', 'fair', 'damaged'];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

interface Props {
  assetId: string;
}

export function AssetDetailPage({ assetId }: Props): React.JSX.Element {
  const query = useAsset(assetId);
  const [action, setAction] = React.useState<'assign' | 'return' | 'transfer' | 'status' | null>(null);

  if (query.isLoading) {
    return <EmptyState title="Loading" description="Fetching the asset." />;
  }
  const asset = query.data;
  if (!asset) {
    return <EmptyState title="Not found" description="This asset does not exist, or is not yours to see." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={asset.name}
        description={`${asset.asset_code} · ${asset.asset_tag} · ${asset.category.name}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {asset.status === 'available' ? (
              <Can permission="assets:assign">
                <Button size="sm" onClick={() => setAction('assign')}>
                  Assign
                </Button>
              </Can>
            ) : null}
            {asset.status === 'assigned' ? (
              <>
                <Can permission="assets:return">
                  <Button size="sm" onClick={() => setAction('return')}>
                    Return
                  </Button>
                </Can>
                <Can permission="assets:transfer">
                  <Button size="sm" variant="outline" onClick={() => setAction('transfer')}>
                    Transfer
                  </Button>
                </Can>
              </>
            ) : null}
            <Can anyOf={['assets:retire', 'assets:dispose']}>
              <Button size="sm" variant="outline" onClick={() => setAction('status')}>
                Change status
              </Button>
            </Can>
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Status" value={<Badge>{ASSET_STATUS_LABELS[asset.status]}</Badge>} />
            <Row
              label="Condition"
              value={<Badge variant="outline">{ASSET_CONDITION_LABELS[asset.condition]}</Badge>}
            />
            <Row label="Brand" value={asset.brand ?? '—'} />
            <Row label="Model" value={asset.model ?? '—'} />
            <Row label="Serial" value={asset.serial_number ?? '—'} />
            <Row label="Type" value={asset.asset_type ?? '—'} />
            <Row label="Location" value={asset.location ?? '—'} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Purchase &amp; warranty</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Purchased" value={asset.purchase_date ?? '—'} />
            <Row label="Cost" value={asset.purchase_cost ?? '—'} />
            <Row label="Vendor" value={asset.vendor ?? '—'} />
            <Row label="Warranty start" value={asset.warranty_start ?? '—'} />
            <Row label="Warranty end" value={asset.warranty_end ?? '—'} />
            <Row
              label="Warranty"
              value={
                <Badge variant={asset.warranty_state === 'expired' ? 'destructive' : 'outline'}>
                  {WARRANTY_STATE_LABELS[asset.warranty_state]}
                </Badge>
              }
            />
            <Row label="Provider" value={asset.warranty_provider ?? '—'} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Assignment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {asset.current_assignment ? (
              <>
                <Row label="Held by" value={asset.assigned_to?.full_name ?? '—'} />
                <Row label="Since" value={asset.current_assignment.assigned_date} />
                <Row label="Expected back" value={asset.current_assignment.expected_return_date ?? '—'} />
                <Row
                  label="Condition when issued"
                  value={ASSET_CONDITION_LABELS[asset.current_assignment.condition_at_assignment]}
                />
              </>
            ) : (
              <p className="text-muted-foreground">Not currently assigned to anybody.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {action ? (
        <ActionPanel
          assetId={asset.id}
          action={action}
          allowedTransitions={asset.allowed_transitions}
          onDone={() => setAction(null)}
        />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            {asset.history.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nothing recorded yet.</p>
            ) : (
              <ol className="space-y-3">
                {asset.history.map((entry) => (
                  <li key={entry.id} className="flex items-start justify-between gap-4 text-sm">
                    <div>
                      <p className="font-medium capitalize">{entry.event.replace(/_/g, ' ')}</p>
                      {entry.previous_value || entry.new_value ? (
                        <p className="text-muted-foreground text-xs">
                          {entry.previous_value ?? '—'} → {entry.new_value ?? '—'}
                        </p>
                      ) : null}
                      {entry.notes ? <p className="text-muted-foreground">{entry.notes}</p> : null}
                    </div>
                    <span className="text-muted-foreground shrink-0 text-xs">
                      {new Date(entry.created_at).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Maintenance</CardTitle>
          </CardHeader>
          <CardContent>
            {asset.maintenance.length === 0 ? (
              <p className="text-muted-foreground text-sm">No maintenance recorded.</p>
            ) : (
              <ul className="space-y-2">
                {asset.maintenance.map((record) => (
                  <li key={record.id} className="flex items-center justify-between gap-4 text-sm">
                    <div>
                      <p className="capitalize">{record.maintenance_type}</p>
                      <p className="text-muted-foreground text-xs">
                        {record.start_date}
                        {record.end_date ? ` → ${record.end_date}` : ''}
                      </p>
                    </div>
                    <Badge variant="outline">{record.status}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

interface PanelProps {
  assetId: string;
  action: 'assign' | 'return' | 'transfer' | 'status';
  allowedTransitions: AssetStatus[];
  onDone: () => void;
}

function ActionPanel({ assetId, action, allowedTransitions, onDone }: PanelProps): React.JSX.Element {
  const assign = useAssignAsset();
  const processReturn = useReturnAsset();
  const transfer = useTransferAsset();
  const changeStatus = useChangeAssetStatus();

  const [employeeId, setEmployeeId] = React.useState('');
  const [condition, setCondition] = React.useState<AssetCondition>('good');
  const [when, setWhen] = React.useState(today());
  const [expected, setExpected] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [status, setStatus] = React.useState<AssetStatus>(allowedTransitions[0] ?? 'available');
  const [notes, setNotes] = React.useState('');

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const done = { onSuccess: onDone };
    if (action === 'assign') {
      assign.mutate(
        {
          assetId,
          payload: {
            employee_id: employeeId,
            assigned_date: when,
            condition_at_assignment: condition,
            expected_return_date: expected || null,
            notes: notes || null,
          },
        },
        done,
      );
    } else if (action === 'return') {
      processReturn.mutate(
        {
          assetId,
          payload: {
            return_date: when,
            condition_at_return: condition,
            damage_details: condition === 'damaged' ? reason : null,
            notes: notes || null,
          },
        },
        done,
      );
    } else if (action === 'transfer') {
      transfer.mutate(
        {
          assetId,
          payload: {
            to_employee_id: employeeId,
            transfer_date: when,
            condition_at_transfer: condition,
            reason: reason || null,
            notes: notes || null,
          },
        },
        done,
      );
    } else {
      changeStatus.mutate({ assetId, payload: { status, reason, condition } }, done);
    }
  };

  const titles = {
    assign: 'Assign this asset',
    return: 'Process a return',
    transfer: 'Transfer to another employee',
    status: 'Change status',
  } as const;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{titles[action]}</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
          {action === 'assign' || action === 'transfer' ? (
            <div className="space-y-2">
              <EmployeePicker id="employee" value={employeeId} onChange={setEmployeeId} />
              <p className="text-muted-foreground text-xs">
                The server checks the employee is active before issuing anything.
              </p>
            </div>
          ) : null}

          {action !== 'status' ? (
            <div className="space-y-2">
              <Label htmlFor="when">Date</Label>
              <Input id="when" type="date" value={when} onChange={(e) => setWhen(e.target.value)} required />
            </div>
          ) : null}

          {action === 'assign' ? (
            <div className="space-y-2">
              <Label htmlFor="expected">Expected return (optional)</Label>
              <Input
                id="expected"
                type="date"
                min={when}
                value={expected}
                onChange={(event) => setExpected(event.target.value)}
              />
            </div>
          ) : null}

          {action === 'status' ? (
            <div className="space-y-2">
              <Label htmlFor="status">New status</Label>
              <select
                id="status"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={status}
                onChange={(event) => setStatus(event.target.value as AssetStatus)}
              >
                {allowedTransitions.map((option) => (
                  <option key={option} value={option}>
                    {ASSET_STATUS_LABELS[option]}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground text-xs">
                Only the moves the server will accept from here.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="condition">Condition</Label>
              <select
                id="condition"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={condition}
                onChange={(event) => setCondition(event.target.value as AssetCondition)}
              >
                {CONDITIONS.map((option) => (
                  <option key={option} value={option}>
                    {ASSET_CONDITION_LABELS[option]}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="reason">
              {action === 'status' ? 'Reason (required)' : 'Reason / damage details'}
            </Label>
            <Textarea
              id="reason"
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required={action === 'status'}
            />
          </div>

          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea id="notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit">Save</Button>
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useMaintenanceRecords, useScheduleMaintenance, useUpdateMaintenance } from '@/features/assets/hooks';
import {
  MAINTENANCE_STATUS_LABELS,
  MAINTENANCE_TYPE_LABELS,
  type Maintenance,
  type MaintenanceStatus,
  type MaintenanceType,
} from '@/features/assets/types';

/**
 * Maintenance.
 *
 * Starting a job takes the asset off the floor and, if somebody was holding it,
 * ends that custody -- the register must never claim a person has a laptop that
 * is in a repair shop. Completing one releases it, back to available unless
 * something else is chosen. Both of those happen on the server; this screen
 * only asks for them.
 */

const TYPES: MaintenanceType[] = ['preventive', 'repair', 'upgrade', 'inspection', 'other'];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AssetMaintenancePage(): React.JSX.Element {
  const [statusFilter, setStatusFilter] = React.useState<MaintenanceStatus | ''>('');
  const [dueOnly, setDueOnly] = React.useState(false);

  const query = useMaintenanceRecords({
    status: statusFilter || undefined,
    due_only: dueOnly || undefined,
  });
  const schedule = useScheduleMaintenance();
  const update = useUpdateMaintenance();

  const [form, setForm] = React.useState({
    asset_id: '',
    maintenance_type: 'repair' as MaintenanceType,
    start_date: today(),
    vendor: '',
    cost: '',
    description: '',
    start_now: false,
  });

  const rows = query.data?.items ?? [];

  const columns: DataTableColumn<Maintenance>[] = [
    {
      id: 'type',
      header: 'Type',
      cell: (row) => MAINTENANCE_TYPE_LABELS[row.maintenance_type],
    },
    { id: 'start', header: 'Start', cell: (row) => row.start_date },
    { id: 'end', header: 'End', cell: (row) => row.end_date ?? '—' },
    { id: 'vendor', header: 'Vendor', cell: (row) => row.vendor ?? '—' },
    { id: 'cost', header: 'Cost', cell: (row) => row.cost ?? '—' },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'completed' ? 'secondary' : 'outline'}>
          {MAINTENANCE_STATUS_LABELS[row.status]}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) =>
        row.status === 'completed' || row.status === 'cancelled' ? null : (
          <Can permission="assets:maintain">
            <div className="flex justify-end gap-2">
              {row.status === 'scheduled' ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => update.mutate({ maintenanceId: row.id, payload: { status: 'in_progress' } })}
                >
                  Start
                </Button>
              ) : null}
              <Button
                size="sm"
                onClick={() =>
                  update.mutate({
                    maintenanceId: row.id,
                    payload: {
                      status: 'completed',
                      end_date: today(),
                      resulting_condition: 'good',
                    },
                  })
                }
              >
                Complete
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => update.mutate({ maintenanceId: row.id, payload: { status: 'cancelled' } })}
              >
                Cancel
              </Button>
            </div>
          </Can>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Asset maintenance"
        description="Scheduled and in-progress work. Starting a job takes the asset out of service."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Records" value={query.data?.meta.total_items ?? 0} />
        <StatCard label="In progress" value={rows.filter((row) => row.status === 'in_progress').length} />
        <StatCard label="Scheduled" value={rows.filter((row) => row.status === 'scheduled').length} />
      </div>

      <Can permission="assets:maintain">
        <Card>
          <CardHeader>
            <CardTitle>Schedule maintenance</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4 sm:grid-cols-3"
              onSubmit={(event) => {
                event.preventDefault();
                schedule.mutate(
                  {
                    asset_id: form.asset_id,
                    maintenance_type: form.maintenance_type,
                    start_date: form.start_date,
                    vendor: form.vendor || null,
                    cost: form.cost || null,
                    description: form.description || null,
                    start_now: form.start_now,
                  },
                  {
                    onSuccess: () => setForm((current) => ({ ...current, asset_id: '', description: '' })),
                  },
                );
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="asset-id">Asset ID</Label>
                <Input
                  id="asset-id"
                  value={form.asset_id}
                  onChange={(event) => setForm({ ...form, asset_id: event.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">Type</Label>
                <select
                  id="type"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.maintenance_type}
                  onChange={(event) =>
                    setForm({ ...form, maintenance_type: event.target.value as MaintenanceType })
                  }
                >
                  {TYPES.map((type) => (
                    <option key={type} value={type}>
                      {MAINTENANCE_TYPE_LABELS[type]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="start">Start date</Label>
                <Input
                  id="start"
                  type="date"
                  value={form.start_date}
                  onChange={(event) => setForm({ ...form, start_date: event.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="vendor">Vendor</Label>
                <Input
                  id="vendor"
                  value={form.vendor}
                  onChange={(event) => setForm({ ...form, vendor: event.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cost">Cost</Label>
                <Input
                  id="cost"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.cost}
                  onChange={(event) => setForm({ ...form, cost: event.target.value })}
                />
              </div>
              <div className="flex items-end gap-2">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.start_now}
                    onChange={(event) => setForm({ ...form, start_now: event.target.checked })}
                  />
                  Start immediately
                </label>
              </div>
              <div className="space-y-2 sm:col-span-3">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  rows={2}
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </div>
              <div className="sm:col-span-3">
                <Button type="submit" disabled={schedule.isPending || !form.asset_id}>
                  {schedule.isPending ? 'Saving…' : 'Schedule'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </Can>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="status-filter">Status</Label>
          <select
            id="status-filter"
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as MaintenanceStatus | '')}
          >
            <option value="">All</option>
            {(Object.keys(MAINTENANCE_STATUS_LABELS) as MaintenanceStatus[]).map((status) => (
              <option key={status} value={status}>
                {MAINTENANCE_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input type="checkbox" checked={dueOnly} onChange={(e) => setDueOnly(e.target.checked)} />
          Due only
        </label>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No maintenance records"
        emptyDescription="Nothing is scheduled or in progress."
      />
    </div>
  );
}

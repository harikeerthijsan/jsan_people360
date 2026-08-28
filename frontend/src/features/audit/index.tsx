'use client';

import { Download } from 'lucide-react';
import * as React from 'react';

import { usePermitted } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from '@/components/ui/sonner';
import { useQuery } from '@tanstack/react-query';
import { api, apiClient } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';

/**
 * The audit trail, readable by the people whose job it is to read it.
 *
 * The trail has been written since Phase 1; this screen is the other half the
 * audit found missing. Read-only by construction — the API has no write
 * endpoint for it — and exporting is a separate permission because handing the
 * whole trail to a spreadsheet is a bigger act than scrolling it.
 */

export interface AuditRow {
  id: string;
  created_at: string;
  action: string;
  outcome: string;
  actor_id: string | null;
  actor_email: string | null;
  entity_type: string | null;
  entity_id: string | null;
  description: string | null;
  context: Record<string, unknown> | null;
  request_id: string | null;
  ip_address: string | null;
}

const auditKey = ['audit'] as const;

interface Filters {
  action?: string;
  entity_type?: string;
  page: number;
}

const useAuditTrail = (filters: Filters) =>
  useQuery({
    queryKey: [...auditKey, 'list', filters],
    queryFn: () => api.get<Page<AuditRow>>('/audit', { params: { page_size: 25, ...filters } }),
    placeholderData: (previous) => previous,
  });

const useAuditActions = () =>
  useQuery({
    queryKey: [...auditKey, 'actions'],
    queryFn: () => api.get<string[]>('/audit/actions'),
    staleTime: 10 * 60_000,
  });

export function AuditTrailScreen(): React.JSX.Element {
  const [filters, setFilters] = React.useState<Filters>({ page: 1 });
  const [entityText, setEntityText] = React.useState('');
  const query = useAuditTrail(filters);
  const actions = useAuditActions();
  const canExport = usePermitted({ permission: 'audit:export' });
  const [exporting, setExporting] = React.useState(false);

  const rows = query.data?.items ?? [];

  const download = async (): Promise<void> => {
    setExporting(true);
    try {
      const response = await apiClient.get<Blob>('/audit/export', {
        params: { action: filters.action, entity_type: filters.entity_type },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'audit-trail.csv';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('The export could not be prepared.');
    } finally {
      setExporting(false);
    }
  };

  const columns: DataTableColumn<AuditRow>[] = [
    {
      id: 'when',
      header: 'When',
      cell: (row) => (
        <span className="text-xs whitespace-nowrap">{new Date(row.created_at).toLocaleString()}</span>
      ),
    },
    {
      id: 'action',
      header: 'Action',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs">{row.action}</span>
          {row.outcome !== 'success' ? <Badge variant="destructive">{row.outcome}</Badge> : null}
        </div>
      ),
    },
    {
      id: 'actor',
      header: 'Who',
      cell: (row) => row.actor_email ?? <span className="text-muted-foreground text-xs">system</span>,
    },
    {
      id: 'what',
      header: 'What',
      cell: (row) => (
        <div className="max-w-md">
          <p className="truncate text-sm">{row.description ?? '—'}</p>
          {row.entity_type ? (
            <p className="text-muted-foreground text-xs">
              {row.entity_type}
              {row.entity_id ? ` · ${row.entity_id.slice(0, 8)}…` : ''}
            </p>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit trail"
        description="Who did what, when. Append-only — nothing here can be edited, including by administrators."
        actions={
          canExport ? (
            <Button variant="outline" onClick={() => void download()} disabled={exporting}>
              <Download className="mr-2 size-4" aria-hidden="true" />
              Export CSV
            </Button>
          ) : null
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <select
          aria-label="Action"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={filters.action ?? ''}
          onChange={(event) =>
            setFilters((current) => ({
              ...current,
              action: event.target.value || undefined,
              page: 1,
            }))
          }
        >
          <option value="">Any action</option>
          {(actions.data ?? []).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <Input
          aria-label="Entity type"
          className="h-9 w-56"
          placeholder="Entity type, e.g. employee"
          value={entityText}
          onChange={(event) => setEntityText(event.target.value)}
          onBlur={() =>
            setFilters((current) => ({
              ...current,
              entity_type: entityText.trim() || undefined,
              page: 1,
            }))
          }
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              setFilters((current) => ({
                ...current,
                entity_type: entityText.trim() || undefined,
                page: 1,
              }));
            }
          }}
        />
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="Nothing recorded"
        emptyDescription="No audited events match these filters."
      />

      {query.data ? (
        <Pagination
          meta={query.data.meta}
          onPageChange={(page) => setFilters((current) => ({ ...current, page }))}
          itemLabel="events"
          disabled={query.isFetching}
        />
      ) : null}
    </div>
  );
}

'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { routes } from '@/config/site';
import { useAssetCategories, useAssets } from '@/features/assets/hooks';
import {
  ASSET_CONDITION_LABELS,
  ASSET_STATUS_LABELS,
  type Asset,
  type AssetCondition,
  type AssetFilters,
  type AssetStatus,
} from '@/features/assets/types';

/**
 * The asset register.
 *
 * **Every filter goes to the server.** §5 of the brief is explicit that the
 * register must not be loaded into the browser, and it is right: an inventory
 * grows without bound, and a client-side filter over one page of it would
 * quietly search only that page while looking like it searched everything.
 *
 * Categories come from the API rather than a constant, per §2. The status and
 * condition lists are enums the server publishes in its schema, so they are
 * safe as literals here -- they cannot drift without a migration.
 */

const STATUSES: AssetStatus[] = [
  'available',
  'assigned',
  'reserved',
  'under_maintenance',
  'damaged',
  'lost',
  'retired',
  'disposed',
];

const CONDITIONS: AssetCondition[] = ['new', 'excellent', 'good', 'fair', 'damaged'];

function statusTone(status: AssetStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'damaged' || status === 'lost') return 'destructive';
  if (status === 'assigned') return 'default';
  if (status === 'retired' || status === 'disposed') return 'outline';
  return 'secondary';
}

export function AssetRegisterPage(): React.JSX.Element {
  const router = useRouter();
  const categories = useAssetCategories();

  const [filters, setFilters] = React.useState<AssetFilters>({ page: 1, page_size: 20 });
  const [search, setSearch] = React.useState('');

  // Debounced so typing does not fire a request per keystroke, while the
  // filtering itself still happens on the server.
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((current) => ({ ...current, search: search.trim() || undefined, page: 1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useAssets(filters);
  const page = query.data;

  const set = <K extends keyof AssetFilters>(key: K, value: AssetFilters[K]): void =>
    setFilters((current) => ({ ...current, [key]: value, page: 1 }));

  const columns: DataTableColumn<Asset>[] = [
    { id: 'tag', header: 'Tag', cell: (row) => <span className="tabular-nums">{row.asset_tag}</span> },
    {
      id: 'name',
      header: 'Asset',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">{row.asset_code}</p>
        </div>
      ),
    },
    { id: 'category', header: 'Category', cell: (row) => row.category.name },
    { id: 'make', header: 'Make', cell: (row) => [row.brand, row.model].filter(Boolean).join(' ') || '—' },
    { id: 'serial', header: 'Serial', cell: (row) => row.serial_number ?? '—' },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant={statusTone(row.status)}>{ASSET_STATUS_LABELS[row.status]}</Badge>,
    },
    {
      id: 'condition',
      header: 'Condition',
      cell: (row) => <Badge variant="outline">{ASSET_CONDITION_LABELS[row.condition]}</Badge>,
    },
    { id: 'holder', header: 'Assigned to', cell: (row) => row.assigned_to?.full_name ?? '—' },
    { id: 'location', header: 'Location', cell: (row) => row.location ?? '—' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Asset register"
        description="Every asset the company owns, with its current holder and condition."
        actions={<Button onClick={() => router.push(routes.assetNew)}>Register an asset</Button>}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="asset-search">Search</Label>
          <Input
            id="asset-search"
            placeholder="Tag, code, name, serial or model"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-category">Category</Label>
          <select
            id="asset-category"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={filters.category_id ?? ''}
            onChange={(event) => set('category_id', event.target.value || undefined)}
          >
            <option value="">All categories</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-status">Status</Label>
          <select
            id="asset-status"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={filters.status ?? ''}
            onChange={(event) => set('status', (event.target.value || undefined) as AssetStatus)}
          >
            <option value="">All statuses</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {ASSET_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-condition">Condition</Label>
          <select
            id="asset-condition"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={filters.condition ?? ''}
            onChange={(event) => set('condition', (event.target.value || undefined) as AssetCondition)}
          >
            <option value="">Any condition</option>
            {CONDITIONS.map((condition) => (
              <option key={condition} value={condition}>
                {ASSET_CONDITION_LABELS[condition]}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-location">Location</Label>
          <Input
            id="asset-location"
            value={filters.location ?? ''}
            onChange={(event) => set('location', event.target.value || undefined)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-vendor">Vendor</Label>
          <Input
            id="asset-vendor"
            value={filters.vendor ?? ''}
            onChange={(event) => set('vendor', event.target.value || undefined)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="asset-assigned">Assignment</Label>
          <select
            id="asset-assigned"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={filters.assigned === undefined ? '' : String(filters.assigned)}
            onChange={(event) =>
              set('assigned', event.target.value === '' ? undefined : event.target.value === 'true')
            }
          >
            <option value="">Assigned and unassigned</option>
            <option value="true">Assigned</option>
            <option value="false">Unassigned</option>
          </select>
        </div>
        <div className="flex items-end">
          <Button
            variant="outline"
            onClick={() => {
              setSearch('');
              setFilters({ page: 1, page_size: 20 });
            }}
          >
            Clear filters
          </Button>
        </div>
      </div>

      <DataTable
        rows={page?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        onRowClick={(row) => router.push(routes.assetDetail(row.id))}
        emptyTitle="No assets found"
        emptyDescription="Nothing matches these filters. Clear them, or register an asset."
      />

      {page && page.meta.total_pages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page.meta.page} of {page.meta.total_pages} · {page.meta.total_items} assets
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!page.meta.has_previous}
              onClick={() => setFilters((c) => ({ ...c, page: (c.page ?? 1) - 1 }))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!page.meta.has_next}
              onClick={() => setFilters((c) => ({ ...c, page: (c.page ?? 1) + 1 }))}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

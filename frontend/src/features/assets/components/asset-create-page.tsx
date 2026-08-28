'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { PageHeader } from '@/components/common/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { routes } from '@/config/site';
import { useAssetCategories, useCreateAsset } from '@/features/assets/hooks';
import { ASSET_CONDITION_LABELS, type AssetCondition, type AssetCreateInput } from '@/features/assets/types';

/**
 * Register an asset.
 *
 * The required set matches §7: name, category, tag, condition, status. Every
 * other field is optional, because an organization entering a backlog of
 * existing kit rarely has the purchase paperwork to hand.
 *
 * Uniqueness of the tag and the serial is checked by the server, which owns the
 * constraint. The form surfaces the refusal rather than trying to predict it --
 * a client-side check would be a race against another administrator typing the
 * same tag.
 */

const CONDITIONS: AssetCondition[] = ['new', 'excellent', 'good', 'fair', 'damaged'];

export function AssetCreatePage(): React.JSX.Element {
  const router = useRouter();
  const categories = useAssetCategories();
  const create = useCreateAsset();

  const [form, setForm] = React.useState<AssetCreateInput>({
    name: '',
    category_id: '',
    asset_tag: '',
    condition: 'new',
    status: 'available',
  });

  const set = <K extends keyof AssetCreateInput>(key: K, value: AssetCreateInput[K]): void =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    create.mutate(form, {
      onSuccess: (asset) => router.push(routes.assetDetail(asset.id)),
    });
  };

  const ready = form.name.length >= 2 && form.category_id !== '' && form.asset_tag.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Register an asset"
        description="The asset code is generated. The tag is yours and must be unique."
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Asset details</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
            <div className="space-y-2">
              <Label htmlFor="name">Asset name *</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(event) => set('name', event.target.value)}
                required
                minLength={2}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="tag">Asset tag *</Label>
              <Input
                id="tag"
                value={form.asset_tag}
                onChange={(event) => set('asset_tag', event.target.value)}
                required
                placeholder="The label on the thing itself"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="category">Category *</Label>
              <select
                id="category"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={form.category_id}
                onChange={(event) => set('category_id', event.target.value)}
                required
              >
                <option value="">Choose a category</option>
                {(categories.data ?? []).map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="condition">Condition *</Label>
              <select
                id="condition"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={form.condition}
                onChange={(event) => set('condition', event.target.value as AssetCondition)}
              >
                {CONDITIONS.map((condition) => (
                  <option key={condition} value={condition}>
                    {ASSET_CONDITION_LABELS[condition]}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="brand">Brand</Label>
              <Input id="brand" onChange={(event) => set('brand', event.target.value || null)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Input id="model" onChange={(event) => set('model', event.target.value || null)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="serial">Serial number</Label>
              <Input
                id="serial"
                onChange={(event) => set('serial_number', event.target.value || null)}
                placeholder="Unique where present"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="location">Location</Label>
              <Input id="location" onChange={(event) => set('location', event.target.value || null)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="purchase-date">Purchase date</Label>
              <Input
                id="purchase-date"
                type="date"
                max={new Date().toISOString().slice(0, 10)}
                onChange={(event) => set('purchase_date', event.target.value || null)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="cost">Purchase cost</Label>
              <Input
                id="cost"
                type="number"
                min="0"
                step="0.01"
                onChange={(event) => set('purchase_cost', event.target.value || null)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="vendor">Vendor</Label>
              <Input id="vendor" onChange={(event) => set('vendor', event.target.value || null)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="warranty-provider">Warranty provider</Label>
              <Input
                id="warranty-provider"
                onChange={(event) => set('warranty_provider', event.target.value || null)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="warranty-start">Warranty start</Label>
              <Input
                id="warranty-start"
                type="date"
                onChange={(event) => set('warranty_start', event.target.value || null)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="warranty-end">Warranty end</Label>
              <Input
                id="warranty-end"
                type="date"
                min={form.warranty_start ?? undefined}
                onChange={(event) => set('warranty_end', event.target.value || null)}
              />
            </div>

            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="notes">Notes</Label>
              <Textarea id="notes" rows={3} onChange={(event) => set('notes', event.target.value || null)} />
            </div>

            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" disabled={!ready || create.isPending}>
                {create.isPending ? 'Registering…' : 'Register asset'}
              </Button>
              <Button type="button" variant="outline" onClick={() => router.push(routes.assets)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

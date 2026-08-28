import * as React from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface DetailItem {
  label: string;
  /** Rendered as-is. Pass a node for badges, links or formatted values. */
  value: React.ReactNode;
  /** Span both columns for long values such as an address. */
  wide?: boolean;
}

interface DetailSectionProps {
  title: string;
  items: DetailItem[];
  className?: string;
}

/**
 * A labelled group of read-only fields.
 *
 * Rendered as a real description list so the label/value relationship is
 * available to assistive technology rather than only implied by layout.
 * Empty values render an em dash instead of collapsing, which keeps the grid
 * aligned and makes "not set" visible rather than ambiguous.
 */
export function DetailSection({ title, items, className }: DetailSectionProps): React.JSX.Element {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {items.map((item) => (
            <div key={item.label} className={cn('min-w-0 space-y-1', item.wide && 'sm:col-span-2')}>
              <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                {item.label}
              </dt>
              <dd className="text-sm break-words">
                {item.value === null || item.value === undefined || item.value === '' ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  item.value
                )}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

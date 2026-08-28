import * as React from 'react';

import { UserAvatar } from '@/components/common/user-avatar';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface ProfileCardProps {
  name: string;
  /** Job title, or whatever best identifies the person's role. */
  subtitle?: string | null;
  photoUrl?: string | null;
  /** Badges: status, staff code, administrator marker. */
  badges?: React.ReactNode;
  /** Key/value pairs shown on the right, e.g. joining date. */
  facts?: { label: string; value: React.ReactNode }[];
  /** Buttons aligned to the end of the header. */
  actions?: React.ReactNode;
  className?: string;
}

/**
 * The banner at the top of a person's page.
 *
 * Kept separate from `DetailSection` because it is a summary, not a field list:
 * it leads with identity so the reader knows whose record they are looking at
 * before any of the detail below.
 */
export function ProfileCard({
  name,
  subtitle,
  photoUrl,
  badges,
  facts,
  actions,
  className,
}: ProfileCardProps): React.JSX.Element {
  return (
    <Card className={className}>
      <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-center">
        <UserAvatar name={name} photoUrl={photoUrl} size="xl" className="shrink-0" />

        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-xl font-semibold tracking-tight">{name}</h2>
            {badges}
          </div>
          {subtitle ? <p className="text-muted-foreground text-sm">{subtitle}</p> : null}
        </div>

        {facts && facts.length > 0 ? (
          <dl
            className={cn(
              'grid shrink-0 gap-x-6 gap-y-2 text-sm',
              facts.length > 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-1',
            )}
          >
            {facts.map((fact) => (
              <div key={fact.label} className="flex flex-col">
                <dt className="text-muted-foreground text-xs tracking-wide uppercase">{fact.label}</dt>
                <dd className="font-medium">{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </CardContent>
    </Card>
  );
}

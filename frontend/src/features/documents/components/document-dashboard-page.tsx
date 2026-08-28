'use client';

import { AlertTriangle, CalendarClock, ClipboardCheck, HardDrive } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { StatCardSkeleton } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDocumentDashboard } from '@/features/documents/hooks/use-documents';
import { formatBytes, type CountByLabel } from '@/features/documents/types/document.types';

const BASE_PATH = '/documents';

/**
 * A horizontal bar breakdown.
 *
 * Each bar links to the list filtered the same way, so a number a reader finds
 * surprising is one click from the records behind it.
 */
function Breakdown({
  title,
  items,
  emptyMessage,
  hrefFor,
}: {
  title: string;
  items: CountByLabel[];
  emptyMessage: string;
  hrefFor?: (item: CountByLabel) => string;
}): React.JSX.Element {
  const largest = items.reduce((max, item) => Math.max(max, item.count), 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-muted-foreground text-sm">{emptyMessage}</p>
        ) : (
          <dl className="space-y-3">
            {items.map((item) => {
              const row = (
                <>
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <dt className="truncate">{item.label}</dt>
                    <dd className="text-muted-foreground tabular-nums">{item.count}</dd>
                  </div>
                  <div className="bg-muted mt-1 h-1.5 overflow-hidden rounded-full" aria-hidden="true">
                    <div
                      className="bg-primary h-full rounded-full"
                      style={{
                        width: `${String(largest === 0 ? 0 : (item.count / largest) * 100)}%`,
                      }}
                    />
                  </div>
                </>
              );

              return (
                <div key={item.label}>
                  {hrefFor ? (
                    <Link
                      href={hrefFor(item)}
                      className="hover:text-primary focus-visible:ring-ring block rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                    >
                      {row}
                    </Link>
                  ) : (
                    row
                  )}
                </div>
              );
            })}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

export function DocumentDashboardPage(): React.JSX.Element {
  const stats = useDocumentDashboard();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Document dashboard"
        description="What the vault is holding, and what needs attention."
        actions={
          <Button asChild variant="outline">
            <Link href={BASE_PATH}>View all documents</Link>
          </Button>
        }
      />

      {stats.error ? (
        <ErrorState
          error={stats.error}
          onRetry={() => {
            void stats.refetch();
          }}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats.isPending ? (
              Array.from({ length: 4 }, (_, index) => <StatCardSkeleton key={index} />)
            ) : (
              <>
                <StatCard
                  label="Documents"
                  value={stats.data.total_documents}
                  hint={`${formatBytes(stats.data.total_storage_bytes)} stored, all versions`}
                  icon={HardDrive}
                />
                <StatCard
                  label="Pending review"
                  value={stats.data.pending_review}
                  hint="Uploaded or under review"
                  icon={ClipboardCheck}
                />
                <StatCard
                  label="Expiring soon"
                  value={stats.data.expiring_soon}
                  hint="Within 30 days"
                  icon={CalendarClock}
                />
                <StatCard
                  label="Expired"
                  value={stats.data.expired}
                  hint="Needs a replacement"
                  icon={AlertTriangle}
                />
              </>
            )}
          </div>

          {stats.isPending ? null : (
            <>
              {/* The two figures that mean somebody has to do something, given
                  their own row so they are not lost among the totals. */}
              {stats.data.expired > 0 || stats.data.pending_review > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {stats.data.expired > 0 ? (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`${BASE_PATH}?expiry=expired`}>
                        <AlertTriangle aria-hidden="true" />
                        Review {stats.data.expired} expired
                      </Link>
                    </Button>
                  ) : null}
                  {stats.data.expiring_soon > 0 ? (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`${BASE_PATH}?expiry=expiring_soon`}>
                        <CalendarClock aria-hidden="true" />
                        {stats.data.expiring_soon} expiring soon
                      </Link>
                    </Button>
                  ) : null}
                  {stats.data.pending_review > 0 ? (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`${BASE_PATH}?status=uploaded`}>
                        <ClipboardCheck aria-hidden="true" />
                        {stats.data.pending_review} awaiting review
                      </Link>
                    </Button>
                  ) : null}
                </div>
              ) : null}

              <div className="grid gap-6 lg:grid-cols-2">
                <Breakdown
                  title="By category"
                  items={stats.data.by_category}
                  emptyMessage="No documents uploaded yet."
                />
                <Breakdown
                  title="By status"
                  items={stats.data.by_status}
                  emptyMessage="No documents uploaded yet."
                />
              </div>

              {stats.data.archived > 0 ? (
                <p className="text-muted-foreground text-sm">
                  {stats.data.archived} archived {stats.data.archived === 1 ? 'document is' : 'documents are'}{' '}
                  excluded from these figures.{' '}
                  <Link href={`${BASE_PATH}?view=archived`} className="text-primary hover:underline">
                    View the archive
                  </Link>
                </p>
              ) : null}
            </>
          )}
        </>
      )}
    </div>
  );
}

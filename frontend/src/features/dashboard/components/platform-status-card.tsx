'use client';

import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle } from 'lucide-react';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import { queryKeys } from '@/lib/query-client';

interface DependencyCheck {
  name: string;
  status: 'up' | 'down';
  latency_ms: number | null;
  detail: string | null;
}

interface ReadinessStatus {
  status: 'ready' | 'degraded';
  service: string;
  version: string;
  environment: string;
  timestamp: string;
  checks: DependencyCheck[];
}

/**
 * Live platform readiness, read from the backend's own probe.
 *
 * Doubles as the reference example of the data-fetching pattern every feature
 * module should follow: typed API call, TanStack Query, explicit loading and
 * error states.
 */
export function PlatformStatusCard(): React.JSX.Element {
  const readiness = useQuery({
    queryKey: queryKeys.health.readiness(),
    queryFn: () => api.get<ReadinessStatus>(endpoints.health.ready),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="space-y-1">
            <CardTitle>Platform status</CardTitle>
            <CardDescription>Live readiness of the API and its dependencies.</CardDescription>
          </div>

          {readiness.data ? (
            <Badge variant={readiness.data.status === 'ready' ? 'success' : 'destructive'}>
              {readiness.data.status === 'ready' ? 'Operational' : 'Degraded'}
            </Badge>
          ) : null}
        </div>
      </CardHeader>

      <CardContent>
        {readiness.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : null}

        {readiness.isError ? (
          <ErrorState
            error={readiness.error}
            compact
            onRetry={() => {
              void readiness.refetch();
            }}
          />
        ) : null}

        {readiness.data ? (
          <dl className="divide-border divide-y">
            <div className="flex items-center justify-between py-2.5 first:pt-0">
              <dt className="text-muted-foreground text-sm">API version</dt>
              <dd className="font-mono text-sm">{readiness.data.version}</dd>
            </div>

            <div className="flex items-center justify-between py-2.5">
              <dt className="text-muted-foreground text-sm">Environment</dt>
              <dd className="text-sm font-medium capitalize">{readiness.data.environment}</dd>
            </div>

            {readiness.data.checks.map((check) => (
              <div key={check.name} className="flex items-center justify-between py-2.5 last:pb-0">
                <dt className="text-muted-foreground flex items-center gap-2 text-sm">
                  {check.status === 'up' ? (
                    <CheckCircle2 className="text-success size-4" aria-hidden="true" />
                  ) : (
                    <XCircle className="text-destructive size-4" aria-hidden="true" />
                  )}
                  <span className="capitalize">{check.name}</span>
                </dt>
                <dd className="text-sm">
                  {check.status === 'up' ? (
                    <span className="text-muted-foreground">
                      {check.latency_ms !== null ? `${check.latency_ms.toFixed(0)} ms` : 'Healthy'}
                    </span>
                  ) : (
                    <span className="text-destructive font-medium">Unavailable</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}

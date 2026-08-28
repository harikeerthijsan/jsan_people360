'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import { useMyOffboarding } from '@/features/offboarding/hooks';
import {
  EXIT_DOCUMENT_LABELS,
  RESIGNATION_STATUS_LABELS,
  SETTLEMENT_STATUS_LABELS,
  TASK_STATUS_LABELS,
} from '@/features/offboarding/types';

/**
 * My Offboarding.
 *
 * One person's own exit and nothing else -- the server returns only their case,
 * and only the checklist rows they themselves own. The IT and Finance rows are
 * somebody else's work; showing an employee a list of tasks they cannot act on
 * would be an invitation to chase people about them.
 *
 * Clearance progress is shown as a proportion rather than a percentage alone,
 * because "3 of 21" tells somebody where they are and "14%" does not.
 */

export function MyOffboardingPage(): React.JSX.Element {
  const router = useRouter();
  const query = useMyOffboarding();

  if (query.isLoading) {
    return <EmptyState title="Loading" description="Fetching your offboarding status." />;
  }

  const data = query.data;
  if (!data?.resignation) {
    return (
      <EmptyState
        title="No offboarding in progress"
        description="Nothing to show here unless you have submitted a resignation."
        action={{ label: 'Go to resignation', onClick: () => router.push(routes.myResignation) }}
      />
    );
  }

  const { resignation, clearance } = data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Offboarding"
        description={
          data.case_code
            ? `${data.case_code} — last working day ${data.last_working_day ?? 'to be confirmed'}`
            : 'Your resignation is still being reviewed.'
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Resignation" value={RESIGNATION_STATUS_LABELS[resignation.status]} />
        <StatCard label="Last working day" value={data.last_working_day ?? 'Awaiting HR'} />
        <StatCard
          label="Notice remaining"
          value={resignation.notice ? `${String(resignation.notice.remaining_days)} days` : '—'}
        />
        <StatCard
          label="Clearance"
          value={clearance ? `${String(clearance.percent)}%` : '—'}
          hint={
            clearance
              ? `${String(
                  clearance.tasks_settled + clearance.assets_settled + clearance.access_settled,
                )} of ${String(
                  clearance.tasks_total + clearance.assets_total + clearance.access_total,
                )} items settled`
              : undefined
          }
        />
      </div>

      {data.pending_actions.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Pending actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.pending_actions.map((action) => (
              <div key={action.key} className="flex items-center justify-between gap-4">
                <span className="text-sm">{action.label}</span>
                <Button asChild size="sm" variant="outline">
                  <Link href={action.link}>Open</Link>
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>My tasks</CardTitle>
          </CardHeader>
          <CardContent>
            {data.my_tasks.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Nothing assigned to you. The remaining clearance is with HR, IT, Admin and Finance.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.my_tasks.map((task) => (
                  <li key={task.id} className="flex items-center justify-between gap-4 text-sm">
                    <span>{task.title}</span>
                    <Badge variant={task.status === 'completed' ? 'secondary' : 'outline'}>
                      {TASK_STATUS_LABELS[task.status]}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Exit documents</CardTitle>
          </CardHeader>
          <CardContent>
            {data.exit_documents.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Your documents appear here once HR has released them.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.exit_documents.map((document) => (
                  <li key={document.id} className="flex items-center justify-between gap-4 text-sm">
                    <span>{EXIT_DOCUMENT_LABELS[document.document_type]}</span>
                    {document.document_id ? (
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/employee/documents?document=${document.document_id}`}>Download</Link>
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 flex items-center justify-between gap-4 border-t pt-4 text-sm">
              <span className="text-muted-foreground">Final settlement</span>
              <Badge variant="outline">
                {data.settlement_status ? SETTLEMENT_STATUS_LABELS[data.settlement_status] : 'Not started'}
              </Badge>
            </div>
            {/*
             * The exit interview page existed with no way in -- the audit
             * found it reachable only by typing the URL. The offboarding
             * screen is where the person already is when it becomes relevant.
             */}
            <div className="mt-4 flex items-center justify-between gap-4 border-t pt-4 text-sm">
              <span className="text-muted-foreground">Exit interview</span>
              <Button asChild size="sm" variant="outline">
                <Link href={routes.myExitInterview}>Open</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

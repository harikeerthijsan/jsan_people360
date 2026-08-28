'use client';

import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { PageHeader } from '@/components/common/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { MASTER_ORDER, MASTER_REGISTRY } from '@/features/organization/config/master-registry';

/** Index of the master-data screens. */
export default function OrganizationOverviewPage(): React.JSX.Element {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Organization"
        description="Master data every other module references. Define it once here."
      />

      <Alert variant="info">
        <AlertTitle>Why this comes first</AlertTitle>
        <AlertDescription>
          Recruitment, employee records, attendance and payroll all point at these records rather than storing
          their own copies of a team or a grade. Keeping them accurate here keeps them consistent everywhere.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {MASTER_ORDER.map((slug) => {
          const config = MASTER_REGISTRY[slug];
          const Icon = config.icon;

          return (
            <Link
              key={slug}
              href={`/organization/${slug}`}
              className="focus-visible:ring-ring rounded-lg focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <Card className="h-full transition-shadow hover:shadow-md">
                <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{config.labelPlural}</CardTitle>
                    <CardDescription className="line-clamp-2">{config.blurb}</CardDescription>
                  </div>
                  <span className="bg-primary-subtle flex size-9 shrink-0 items-center justify-center rounded-md">
                    <Icon className="text-primary size-4" aria-hidden="true" />
                  </span>
                </CardHeader>
                <CardContent>
                  <span className="text-primary inline-flex items-center gap-1 text-sm font-medium">
                    Manage
                    <ArrowRight className="size-3.5" aria-hidden="true" />
                  </span>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

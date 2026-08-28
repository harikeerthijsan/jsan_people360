'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { useAuth } from '@/components/providers/auth-provider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { routes, siteConfig } from '@/config/site';

interface AuthShellProps {
  title: string;
  description: string;
  children: React.ReactNode;
}

/**
 * The frame for unauthenticated pages (sign in, password recovery).
 *
 * A split layout: a brand panel on wide screens, the form card everywhere.
 * Already-authenticated visitors are bounced to the dashboard so a stale
 * bookmark to /login does not present a pointless form.
 */
export function AuthShell({ title, description, children }: AuthShellProps): React.JSX.Element {
  const { status } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (status === 'authenticated') {
      router.replace(routes.dashboard);
    }
  }, [status, router]);

  if (status === 'initialising') {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <LoadingState message="Loading…" />
      </div>
    );
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      {/* Brand panel -- decorative, so it is hidden from assistive technology
          and from narrow viewports entirely. */}
      <section
        className="bg-primary text-primary-foreground relative hidden flex-col justify-between p-12 lg:flex"
        aria-hidden="true"
      >
        <div className="flex items-center gap-3">
          <span className="bg-primary-foreground/15 flex size-10 items-center justify-center rounded-lg text-lg font-bold">
            J
          </span>
          <div className="leading-tight">
            <p className="text-base font-semibold">{siteConfig.name}</p>
            <p className="text-primary-foreground/70 text-sm">{siteConfig.company}</p>
          </div>
        </div>

        <div className="max-w-md space-y-4">
          <h2 className="text-3xl leading-tight font-semibold tracking-tight">
            One platform for the entire employee lifecycle.
          </h2>
          <p className="text-primary-foreground/80">
            Recruitment, onboarding, attendance, leave, performance and offboarding — built on a single,
            auditable foundation.
          </p>
        </div>

        <p className="text-primary-foreground/60 text-xs">
          © {new Date().getFullYear()} {siteConfig.company}. All rights reserved.
        </p>
      </section>

      {/* Form panel */}
      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-md text-sm font-bold">
              J
            </span>
            <span className="text-base font-semibold tracking-tight">{siteConfig.name}</span>
          </div>

          <Card className="border-border shadow-sm">
            <CardHeader className="space-y-1.5 pb-4">
              <CardTitle className="text-xl">{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent>{children}</CardContent>
          </Card>

          <p className="text-muted-foreground mt-6 text-center text-xs">
            Having trouble signing in? Contact your system administrator.
          </p>
        </div>
      </section>
    </div>
  );
}

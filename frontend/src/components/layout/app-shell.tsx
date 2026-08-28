'use client';

import { useRouter, usePathname } from 'next/navigation';
import * as React from 'react';

import { PageTransition } from '@/components/common/page-transition';

import { Header } from '@/components/layout/header';
import { Sidebar } from '@/components/layout/sidebar';
import { LoadingState } from '@/components/common/loading-state';
import { useAuth } from '@/components/providers/auth-provider';
import { routes } from '@/config/site';

/**
 * The authenticated application frame: sidebar, header and content area.
 *
 * It also guards its subtree. This is a *usability* guard, not a security
 * boundary -- it decides what to render, while the API independently authorises
 * every request. Route protection cannot live in Next.js middleware here
 * because the refresh cookie is scoped to the backend's `/api/v1/auth` path and
 * is therefore never sent to the Next.js server.
 */
export function AppShell({ children }: { children: React.ReactNode }): React.JSX.Element {
  const { status, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (status === 'unauthenticated') {
      // Remember where the user was headed so sign-in can return them there.
      const next = encodeURIComponent(pathname);
      router.replace(`${routes.login}?next=${next}`);
    }
  }, [status, pathname, router]);

  if (status === 'initialising') {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <LoadingState message="Restoring your session…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // The effect above is redirecting; render nothing rather than flashing the
    // shell to a signed-out visitor.
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <LoadingState message="Redirecting to sign in…" />
      </div>
    );
  }

  return (
    <div className="bg-background min-h-dvh">
      <Sidebar />

      <div className="lg:pl-(--sidebar-width)">
        <Header />

        <main id="main-content" className="mx-auto w-full max-w-[100rem] px-4 py-6 sm:px-6 lg:px-8">
          <PageTransition>{children}</PageTransition>
        </main>
      </div>
    </div>
  );
}

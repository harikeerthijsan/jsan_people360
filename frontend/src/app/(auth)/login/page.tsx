import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { AuthShell } from '@/components/layout/auth-shell';
import { LoginForm } from '@/features/auth/components/login-form';

export const metadata: Metadata = {
  title: 'Sign in',
  description: 'Sign in to your JSAN People360 account.',
};

export default function LoginPage(): React.JSX.Element {
  return (
    <AuthShell title="Sign in" description="Enter your credentials to access the platform.">
      {/* `LoginForm` reads the `next` search param, which requires a Suspense
          boundary under the App Router. */}
      <Suspense fallback={<LoadingState message="Loading…" className="min-h-64" />}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}

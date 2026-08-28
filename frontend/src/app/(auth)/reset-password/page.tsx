import type { Metadata } from 'next';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { AuthShell } from '@/components/layout/auth-shell';
import { ResetPasswordForm } from '@/features/auth/components/reset-password-form';

export const metadata: Metadata = {
  title: 'Reset password',
  description: 'Choose a new password for your JSAN People360 account.',
};

export default function ResetPasswordPage(): React.JSX.Element {
  return (
    <AuthShell title="Choose a new password" description="Your new password must meet the platform policy.">
      {/* The reset token arrives as a search param, so a Suspense boundary is
          required around the component that reads it. */}
      <Suspense fallback={<LoadingState message="Loading…" className="min-h-64" />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}

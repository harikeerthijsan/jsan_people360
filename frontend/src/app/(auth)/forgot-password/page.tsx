import type { Metadata } from 'next';
import type * as React from 'react';

import { AuthShell } from '@/components/layout/auth-shell';
import { ForgotPasswordForm } from '@/features/auth/components/forgot-password-form';

export const metadata: Metadata = {
  title: 'Forgot password',
  description: 'Request a link to reset your JSAN People360 password.',
};

export default function ForgotPasswordPage(): React.JSX.Element {
  return (
    <AuthShell
      title="Forgot your password?"
      description="Enter your email address and we'll send you a link to reset it."
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}

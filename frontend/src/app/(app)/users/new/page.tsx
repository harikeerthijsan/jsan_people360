import type { Metadata } from 'next';
import type * as React from 'react';

import { UserCreatePage } from '@/features/users/components/user-form-page';

export const metadata: Metadata = {
  title: 'New user',
};

export default function NewUserRoute(): React.JSX.Element {
  return <UserCreatePage />;
}

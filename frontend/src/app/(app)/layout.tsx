import type * as React from 'react';

import { AppShell } from '@/components/layout/app-shell';

/**
 * Layout for every authenticated route.
 *
 * Placing the shell here means each page under `(app)` inherits the sidebar,
 * header and session guard without repeating them.
 */
export default function AppLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <AppShell>{children}</AppShell>;
}

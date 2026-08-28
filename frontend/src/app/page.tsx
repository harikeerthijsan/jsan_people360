import { redirect } from 'next/navigation';

import { routes } from '@/config/site';

/**
 * The root route has no content of its own.
 *
 * It forwards to the dashboard; if the visitor is not signed in, `AppShell`
 * redirects them onward to sign-in.
 */
export default function RootPage(): never {
  redirect(routes.dashboard);
}

/** Domain types for the authentication feature, mirroring the backend schemas. */

import type { UserRecord } from '@/types/user';

/**
 * The signed-in user.
 *
 * An alias rather than a second definition: `/auth/login` and `/users/{id}`
 * return the same `UserRead` payload, and two copies of that shape would drift
 * the first time a field is added.
 */
export type User = UserRecord;

export interface TokenPair {
  access_token: string;
  token_type: string;
  /** Access token lifetime in seconds. */
  expires_in: number;
}

export interface LoginResult {
  tokens: TokenPair;
  user: User;
}

export interface PasswordResetIssued {
  detail: string;
  /** Present only outside production, so the flow is testable without email. */
  reset_token: string | null;
}

/** What the rest of the app can observe about the session. */
export type AuthStatus = 'initialising' | 'authenticated' | 'unauthenticated';

export interface RoleSummary {
  id: string;
  key: string;
  name: string;
  is_system: boolean;
  status: string;
}

/**
 * What `/auth/me` answers.
 *
 * Permissions arrive as flat `module:action` strings. A superuser receives the
 * whole catalogue rather than a wildcard, so every consumer -- the guard, the
 * navigation, the role screen -- reasons about one shape instead of two.
 */
export interface Session {
  user: User;
  roles: RoleSummary[];
  permissions: string[];
  is_superuser: boolean;
}

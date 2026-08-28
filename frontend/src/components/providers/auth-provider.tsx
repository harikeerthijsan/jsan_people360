'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { routes } from '@/config/site';
import { authApi } from '@/features/auth/api/auth.api';
import type { LoginPayload } from '@/features/auth/schemas/auth.schemas';
import type { AuthStatus, RoleSummary, User } from '@/features/auth/types/auth.types';
import { onSessionExpired } from '@/lib/api/client';
import { clearAccessToken, setAccessToken } from '@/lib/auth/token-store';

interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<User>;
  logout: (allSessions?: boolean) => Promise<void>;
  /** Replace the cached profile after a self-service update. */
  setUser: (user: User) => void;
  roles: RoleSummary[];
  /** Every permission the session holds, as `module:action`. */
  permissions: ReadonlySet<string>;
  /** True when the session holds this permission. */
  can: (permission: string) => boolean;
  /** True when the session holds at least one of these. */
  canAny: (...permissions: string[]) => boolean;
  /** True when the session holds all of these. */
  canAll: (...permissions: string[]) => boolean;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

/**
 * Owns the client session.
 *
 * The access token lives in memory only. On mount, this provider calls
 * `/auth/refresh` once: the browser sends the HttpOnly refresh cookie, and a
 * successful exchange restores the session after a full page reload without
 * anything sensitive ever being written to `localStorage`.
 */
export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const router = useRouter();
  const [user, setUserState] = React.useState<User | null>(null);
  const [status, setStatus] = React.useState<AuthStatus>('initialising');
  const [roles, setRoles] = React.useState<RoleSummary[]>([]);
  const [permissions, setPermissions] = React.useState<ReadonlySet<string>>(() => new Set());

  /**
   * Load what the session may do.
   *
   * Failure here is deliberately *not* fatal: the caller is authenticated, so
   * the right outcome is a session that can see nothing rather than one thrown
   * back to the login screen. Guards then hide everything, which is the safe
   * direction to fail in.
   */
  const loadPermissions = React.useCallback(async (): Promise<void> => {
    try {
      const session = await authApi.getSession();
      setRoles(session.roles);
      setPermissions(new Set(session.permissions));
    } catch {
      setRoles([]);
      setPermissions(new Set());
    }
  }, []);

  // ---- Session bootstrap --------------------------------------------
  React.useEffect(() => {
    let cancelled = false;

    async function bootstrap(): Promise<void> {
      try {
        const result = await authApi.refresh();
        if (cancelled) return;
        setAccessToken(result.tokens.access_token);
        setUserState(result.user);
        await loadPermissions();
        if (cancelled) return;
        setStatus('authenticated');
      } catch {
        // No usable refresh cookie. This is the normal path for a first-time
        // visitor, so it is not surfaced as an error.
        if (cancelled) return;
        clearAccessToken();
        setUserState(null);
        setRoles([]);
        setPermissions(new Set());
        setStatus('unauthenticated');
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [loadPermissions]);

  // ---- React to a session that expires mid-visit ---------------------
  React.useEffect(
    () =>
      onSessionExpired(() => {
        setUserState(null);
        setRoles([]);
        setPermissions(new Set());
        setStatus('unauthenticated');
        router.replace(routes.login);
      }),
    [router],
  );

  // ---- Actions -------------------------------------------------------
  const login = React.useCallback(
    async (payload: LoginPayload): Promise<User> => {
      const result = await authApi.login(payload);
      setAccessToken(result.tokens.access_token);
      setUserState(result.user);
      // Before `authenticated`, so the first authenticated render already knows
      // which navigation items exist rather than flashing ones it must remove.
      await loadPermissions();
      setStatus('authenticated');
      return result.user;
    },
    [loadPermissions],
  );

  const logout = React.useCallback(
    async (allSessions = false): Promise<void> => {
      try {
        await authApi.logout(allSessions);
      } catch {
        // The local session must end even if the revoke call fails; the token
        // expires server-side regardless.
      } finally {
        clearAccessToken();
        setUserState(null);
        setRoles([]);
        setPermissions(new Set());
        setStatus('unauthenticated');
        router.replace(routes.login);
      }
    },
    [router],
  );

  const setUser = React.useCallback((next: User): void => {
    setUserState(next);
  }, []);

  const can = React.useCallback((permission: string): boolean => permissions.has(permission), [permissions]);
  const canAny = React.useCallback(
    (...wanted: string[]): boolean => wanted.some((item) => permissions.has(item)),
    [permissions],
  );
  const canAll = React.useCallback(
    (...wanted: string[]): boolean => wanted.every((item) => permissions.has(item)),
    [permissions],
  );

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      isAuthenticated: status === 'authenticated' && user !== null,
      login,
      logout,
      setUser,
      roles,
      permissions,
      can,
      canAny,
      canAll,
    }),
    [user, status, login, logout, setUser, roles, permissions, can, canAny, canAll],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access the current session. Throws when used outside the provider. */
export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an <AuthProvider>');
  }
  return context;
}

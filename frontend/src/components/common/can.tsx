'use client';

import { ShieldOff } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { useAuth } from '@/components/providers/auth-provider';

/**
 * Permission guards for the UI.
 *
 * These hide and disable; they do not secure. Every one of them has a matching
 * guard on the endpoint behind it, because anything enforced only in the browser
 * is enforced by whoever has not opened the network tab. What these buy is that
 * a user is never shown a control that will refuse them.
 */

interface CanProps {
  /** Held to render the children. */
  permission?: string;
  /** Any one of these is enough. */
  anyOf?: string[];
  /** All of these are required. */
  allOf?: string[];
  children: React.ReactNode;
  /** Rendered instead when the check fails. Nothing, by default. */
  fallback?: React.ReactNode;
}

/** Render children only when the session holds the required permissions. */
export function Can({
  permission,
  anyOf,
  allOf,
  children,
  fallback = null,
}: CanProps): React.JSX.Element | null {
  const allowed = usePermitted({ permission, anyOf, allOf });
  if (!allowed) return <>{fallback}</>;
  return <>{children}</>;
}

/**
 * The same check as a hook, for the cases a wrapper cannot express -- a
 * `disabled` prop, a column that should not be built, a menu item's presence in
 * an array.
 */
export function usePermitted({
  permission,
  anyOf,
  allOf,
}: Pick<CanProps, 'permission' | 'anyOf' | 'allOf'>): boolean {
  const { can, canAny, canAll } = useAuth();

  if (permission && !can(permission)) return false;
  if (anyOf && anyOf.length > 0 && !canAny(...anyOf)) return false;
  if (allOf && allOf.length > 0 && !canAll(...allOf)) return false;
  // No constraint given means no constraint applied. Callers that build a
  // permission string dynamically rely on this rather than special-casing.
  return true;
}

interface RequirePermissionProps extends Omit<CanProps, 'fallback'> {
  /** What the user was trying to reach, named in the refusal. */
  title?: string;
}

/**
 * Page-level protection.
 *
 * Shows a plain refusal rather than redirecting. A redirect to the dashboard
 * looks like a broken link and sends people to support; saying "you do not have
 * access to this" tells them exactly what to ask for.
 */
export function RequirePermission({
  permission,
  anyOf,
  allOf,
  children,
  title = 'this page',
}: RequirePermissionProps): React.JSX.Element {
  const { status } = useAuth();
  const allowed = usePermitted({ permission, anyOf, allOf });

  // Permissions are loaded before the session is marked authenticated, so
  // anything earlier would refuse a user who simply has not finished loading.
  if (status === 'initialising') return <></>;
  if (allowed) return <>{children}</>;

  return (
    <EmptyState
      icon={ShieldOff}
      title="You do not have access"
      description={`Your roles do not include permission to open ${title}. Ask an administrator if you need it.`}
    />
  );
}

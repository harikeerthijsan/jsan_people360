'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as React from 'react';

import { useAuth } from '@/components/providers/auth-provider';
import { navigation, type NavItem } from '@/config/navigation';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface SidebarNavProps {
  /** Invoked after a navigation, so the mobile drawer can close itself. */
  onNavigate?: () => void;
}

function isActive(pathname: string, item: NavItem): boolean {
  if (pathname === item.href) return true;
  // Section landing pages opt out of prefix matching; without that, a parent
  // like /organization would stay lit on every one of its child routes.
  if (item.exact === true) return false;
  // Otherwise a descendant route counts, so /settings/security keeps Settings lit.
  return pathname.startsWith(`${item.href}/`);
}

function NavLink({ item, active, onNavigate }: { item: NavItem; active: boolean; onNavigate?: () => void }) {
  const Icon = item.icon;

  const content = (
    <>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{item.label}</span>
      {item.badge ? (
        <Badge
          variant="outline"
          className="border-sidebar-border text-sidebar-foreground shrink-0 px-1.5 py-0 text-[10px]"
        >
          {item.badge}
        </Badge>
      ) : null}
    </>
  );

  const baseClass =
    'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

  // Modules that ship later are visible but inert, so the shape of the product
  // is discoverable without offering a dead link.
  if (item.disabled === true) {
    return (
      <span
        className={cn(baseClass, 'text-sidebar-muted/50 cursor-not-allowed')}
        aria-disabled="true"
        title="Available in a future release"
      >
        {content}
      </span>
    );
  }

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        baseClass,
        active
          ? 'bg-sidebar-active text-sidebar-active-foreground'
          : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
      )}
    >
      {content}
    </Link>
  );
}

/** The grouped primary navigation, shared by the sidebar and mobile drawer. */
export function SidebarNav({ onNavigate }: SidebarNavProps): React.JSX.Element {
  const pathname = usePathname();
  const { can } = useAuth();

  /**
   * Sections whose every item is hidden are dropped along with their heading.
   * A lone "Recruitment" label above nothing reads as a broken page rather than
   * as an area the user cannot enter.
   */
  const visible = React.useMemo(
    () =>
      navigation
        .map((section) => ({
          ...section,
          items: section.items.filter(
            (item) =>
              (!item.permission || can(item.permission)) &&
              (item.allOf ?? []).every((permission) => can(permission)),
          ),
        }))
        .filter((section) => section.items.length > 0),
    [can],
  );

  return (
    <nav aria-label="Main navigation" className="flex flex-col gap-6 px-3 py-4">
      {visible.map((section) => (
        <div key={section.id} className="space-y-1">
          <p className="text-sidebar-muted/80 px-3 pb-1 text-[11px] font-semibold tracking-wider uppercase">
            {section.label}
          </p>

          {section.items.map((item) => (
            <NavLink key={item.id} item={item} active={isActive(pathname, item)} onNavigate={onNavigate} />
          ))}
        </div>
      ))}
    </nav>
  );
}

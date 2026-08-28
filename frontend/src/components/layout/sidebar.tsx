import * as React from 'react';

import { Brand } from '@/components/layout/brand';
import { SidebarNav } from '@/components/layout/sidebar-nav';
import { siteConfig } from '@/config/site';
import { cn } from '@/lib/utils';

/**
 * The permanent desktop sidebar.
 *
 * Hidden below the `lg` breakpoint, where {@link MobileNav} presents the same
 * navigation inside a drawer.
 */
export function Sidebar({ className }: { className?: string }): React.JSX.Element {
  return (
    <aside
      className={cn(
        'bg-sidebar text-sidebar-foreground border-sidebar-border fixed inset-y-0 left-0 z-30 hidden w-(--sidebar-width) flex-col border-r lg:flex',
        className,
      )}
    >
      <div className="border-sidebar-border flex h-(--header-height) shrink-0 items-center border-b px-4">
        <Brand />
      </div>

      <div className="flex-1 scrollbar-thin overflow-y-auto">
        <SidebarNav />
      </div>

      <div className="border-sidebar-border shrink-0 border-t px-4 py-3">
        <p className="text-sidebar-muted text-[11px]">
          {siteConfig.shortName} · v0.1.0
          {siteConfig.environment !== 'production' ? (
            <span className="ml-1 uppercase">({siteConfig.environment})</span>
          ) : null}
        </p>
      </div>
    </aside>
  );
}

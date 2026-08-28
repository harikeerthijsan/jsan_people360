'use client';

import * as React from 'react';

import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { MobileNav } from '@/components/layout/mobile-nav';
import { UserMenu } from '@/components/layout/user-menu';
import { Badge } from '@/components/ui/badge';
import { siteConfig } from '@/config/site';

/** The sticky application header: navigation trigger, breadcrumbs, account menu. */
export function Header(): React.JSX.Element {
  return (
    <header className="border-border bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 flex h-(--header-height) items-center gap-3 border-b px-4 backdrop-blur sm:px-6">
      <MobileNav />

      <Breadcrumbs className="hidden flex-1 sm:block" />
      <div className="flex-1 sm:hidden" />

      <div className="flex shrink-0 items-center gap-3">
        {/* A visible environment marker prevents the classic "I thought this
            was staging" incident. */}
        {siteConfig.environment !== 'production' ? (
          <Badge variant="warning" className="hidden uppercase sm:inline-flex">
            {siteConfig.environment}
          </Badge>
        ) : null}

        <UserMenu />
      </div>
    </header>
  );
}

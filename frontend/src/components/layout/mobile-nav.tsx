'use client';

import { Menu } from 'lucide-react';
import * as React from 'react';

import { Brand } from '@/components/layout/brand';
import { SidebarNav } from '@/components/layout/sidebar-nav';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { useDisclosure } from '@/hooks/use-disclosure';

/** The sidebar navigation presented as a drawer on small screens. */
export function MobileNav(): React.JSX.Element {
  const { isOpen, setOpen, close } = useDisclosure(false);

  return (
    <Sheet open={isOpen} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation menu">
          <Menu className="size-5" aria-hidden="true" />
        </Button>
      </SheetTrigger>

      <SheetContent side="left" className="bg-sidebar text-sidebar-foreground border-sidebar-border w-72 p-0">
        <div className="border-sidebar-border flex h-(--header-height) items-center border-b px-4">
          <SheetTitle asChild>
            <Brand />
          </SheetTitle>
        </div>

        <SheetDescription className="sr-only">Primary navigation</SheetDescription>

        <div className="flex-1 scrollbar-thin overflow-y-auto">
          {/* Closing on navigate keeps the drawer from covering the page the
              user just asked for. */}
          <SidebarNav onNavigate={close} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

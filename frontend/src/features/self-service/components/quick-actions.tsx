'use client';

import { CalendarDays, CalendarOff, FileClock, FileUp, UserCog, type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';

/**
 * The five things an employee opens the portal to do.
 *
 * Links rather than buttons with handlers: each is a real destination, so it
 * opens in a new tab, gets a browser history entry and can be bookmarked. Check
 * in and check out are deliberately *not* here -- they are actions rather than
 * destinations, and they live on the attendance card where their state is
 * visible.
 */

interface QuickAction {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
}

const ACTIONS: QuickAction[] = [
  { id: 'leave', label: 'Apply for leave', href: `${routes.myLeave}?apply=1`, icon: CalendarOff },
  { id: 'timesheet', label: 'Fill timesheet', href: routes.myTimesheets, icon: FileClock },
  { id: 'attendance', label: 'My attendance', href: routes.myAttendance, icon: CalendarDays },
  { id: 'document', label: 'Upload document', href: `${routes.myDocuments}?upload=1`, icon: FileUp },
  { id: 'profile', label: 'My profile', href: routes.myProfile, icon: UserCog },
];

export function QuickActions(): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Quick actions</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {ACTIONS.map((action) => (
            <Button asChild className="h-auto flex-col gap-2 py-4" key={action.id} variant="outline">
              <Link href={action.href}>
                <action.icon className="size-5" aria-hidden="true" />
                <span className="text-center text-xs leading-tight">{action.label}</span>
              </Link>
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

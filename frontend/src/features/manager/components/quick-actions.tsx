'use client';

import {
  BriefcaseBusiness,
  CalendarClock,
  CalendarOff,
  ClipboardCheck,
  FileClock,
  TrendingUp,
  Users2,
  type LucideIcon,
} from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { usePermitted } from '@/components/common/can';
import { Button } from '@/components/ui/button';
import { routes } from '@/config/site';

/**
 * The seven things a manager opens the dashboard to do.
 *
 * Each one is hidden when the session cannot use it. That is a courtesy rather
 * than a control -- the endpoint behind every link is guarded and scoped
 * independently -- but offering a Team Lead a link to document completion they
 * will be refused is a worse experience than not offering it.
 */

interface Action {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  permission: string;
}

const ACTIONS: Action[] = [
  {
    id: 'leave',
    label: 'Approve leave',
    href: `${routes.managerLeave}?status=pending`,
    icon: CalendarOff,
    permission: 'leave:approve',
  },
  {
    id: 'timesheets',
    label: 'Approve timesheets',
    href: `${routes.managerTimesheets}?status=submitted`,
    icon: FileClock,
    permission: 'timesheets:approve',
  },
  {
    id: 'regularizations',
    label: 'Review corrections',
    href: routes.managerRegularization,
    icon: ClipboardCheck,
    permission: 'attendance:approve',
  },
  { id: 'team', label: 'View team', href: routes.managerTeam, icon: Users2, permission: 'employees:view' },
  {
    id: 'attendance',
    label: 'View attendance',
    href: routes.managerAttendance,
    icon: CalendarClock,
    permission: 'attendance:approve',
  },
  {
    id: 'performance',
    label: 'Team performance',
    href: routes.managerPerformance,
    icon: TrendingUp,
    permission: 'performance:create',
  },
  {
    id: 'projects',
    label: 'View projects',
    href: routes.managerProjects,
    icon: BriefcaseBusiness,
    permission: 'projects:view',
  },
];

function QuickAction({ action }: { action: Action }): React.JSX.Element | null {
  const allowed = usePermitted({ permission: action.permission });
  if (!allowed) return null;

  const Icon = action.icon;
  return (
    <Button asChild size="sm" variant="outline">
      <Link href={action.href}>
        <Icon className="size-4" aria-hidden="true" />
        {action.label}
      </Link>
    </Button>
  );
}

export function QuickActions(): React.JSX.Element {
  return (
    <nav aria-label="Manager quick actions" className="flex flex-wrap gap-2">
      {ACTIONS.map((action) => (
        <QuickAction action={action} key={action.id} />
      ))}
    </nav>
  );
}

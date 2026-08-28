'use client';

import { ChevronDown, LogOut, MonitorSmartphone, Settings, UserCog } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { useAuth } from '@/components/providers/auth-provider';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/common/modal';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { routes } from '@/config/site';
import { useDisclosure } from '@/hooks/use-disclosure';
import { getInitials } from '@/lib/utils';

/** Account menu in the header: profile links and sign-out. */
export function UserMenu(): React.JSX.Element | null {
  const { user, logout } = useAuth();
  const signOutAll = useDisclosure(false);
  const [isSigningOut, setIsSigningOut] = React.useState(false);

  if (!user) {
    return null;
  }

  const handleSignOut = async (allSessions: boolean): Promise<void> => {
    setIsSigningOut(true);
    try {
      await logout(allSessions);
    } finally {
      setIsSigningOut(false);
      signOutAll.close();
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-auto gap-2 px-2 py-1.5" aria-label="Open account menu">
            <Avatar className="size-8">
              {user.avatar_url ? <AvatarImage src={user.avatar_url} alt="" /> : null}
              <AvatarFallback>{getInitials(user.full_name)}</AvatarFallback>
            </Avatar>

            <span className="hidden min-w-0 flex-col items-start leading-tight sm:flex">
              <span className="max-w-36 truncate text-sm font-medium">{user.full_name}</span>
              <span className="text-muted-foreground max-w-36 truncate text-xs">{user.email}</span>
            </span>

            <ChevronDown className="text-muted-foreground size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="flex flex-col gap-0.5">
            <span className="truncate text-sm">{user.full_name}</span>
            <span className="text-muted-foreground truncate text-xs font-normal">{user.email}</span>
          </DropdownMenuLabel>

          <DropdownMenuSeparator />

          <DropdownMenuItem asChild>
            <Link href={routes.profile}>
              <UserCog aria-hidden="true" />
              My profile
            </Link>
          </DropdownMenuItem>

          <DropdownMenuItem asChild>
            <Link href={routes.settings}>
              <Settings aria-hidden="true" />
              Settings
            </Link>
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuItem onSelect={signOutAll.open}>
            <MonitorSmartphone aria-hidden="true" />
            Sign out everywhere
          </DropdownMenuItem>

          <DropdownMenuItem
            variant="destructive"
            onSelect={() => {
              void handleSignOut(false);
            }}
          >
            <LogOut aria-hidden="true" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={signOutAll.isOpen}
        onOpenChange={signOutAll.setOpen}
        title="Sign out of every device?"
        description="This ends every active session for your account, including any browser or device you are still signed in on."
        confirmLabel="Sign out everywhere"
        isConfirming={isSigningOut}
        destructive
        onConfirm={() => {
          void handleSignOut(true);
        }}
      />
    </>
  );
}

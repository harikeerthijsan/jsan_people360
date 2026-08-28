import * as React from 'react';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn, getInitials } from '@/lib/utils';

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';

const SIZE_CLASS: Record<AvatarSize, string> = {
  sm: 'size-7 text-[10px]',
  md: 'size-9 text-xs',
  lg: 'size-12 text-sm',
  xl: 'size-20 text-xl',
};

interface UserAvatarProps {
  name: string;
  photoUrl?: string | null;
  size?: AvatarSize;
  className?: string;
}

/**
 * A person's photo, falling back to their initials.
 *
 * The `alt` is empty on purpose: the name is always rendered next to the avatar
 * or supplied by the surrounding control, so describing the image again would
 * make a screen reader announce it twice.
 */
export function UserAvatar({ name, photoUrl, size = 'md', className }: UserAvatarProps): React.JSX.Element {
  return (
    <Avatar className={cn(SIZE_CLASS[size], className)}>
      {photoUrl ? <AvatarImage src={photoUrl} alt="" /> : null}
      <AvatarFallback>{getInitials(name)}</AvatarFallback>
    </Avatar>
  );
}

interface UserIdentityProps {
  name: string;
  /** Shown beneath the name -- usually the staff code or email. */
  secondary?: string | null;
  photoUrl?: string | null;
  size?: AvatarSize;
  className?: string;
}

/**
 * Avatar plus name, the pairing every user list row and picker needs.
 *
 * Both text lines truncate so a long name cannot push a table column out of
 * shape.
 */
export function UserIdentity({
  name,
  secondary,
  photoUrl,
  size = 'md',
  className,
}: UserIdentityProps): React.JSX.Element {
  return (
    <div className={cn('flex min-w-0 items-center gap-3', className)}>
      <UserAvatar name={name} photoUrl={photoUrl} size={size} />
      <div className="min-w-0">
        <p className="text-foreground truncate font-medium">{name}</p>
        {secondary ? <p className="text-muted-foreground truncate text-xs">{secondary}</p> : null}
      </div>
    </div>
  );
}

'use client';

import { MoreHorizontal, type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export interface ActionMenuItem {
  /** Stable key, also used as the React key. */
  id: string;
  label: string;
  icon?: LucideIcon;
  /** Renders as a link when set, otherwise as a button. */
  href?: string;
  onSelect?: () => void;
  destructive?: boolean;
  disabled?: boolean;
  /** Draws a divider above this item. */
  separatorBefore?: boolean;
  /**
   * Hides the item entirely.
   *
   * Preferred over rendering it disabled for actions that make no sense in the
   * current state -- offering "Restore" on a live record is noise, not a hint.
   */
  hidden?: boolean;
}

interface ActionMenuProps {
  items: ActionMenuItem[];
  /** Used for the trigger's accessible name, e.g. "Actions for Jane Doe". */
  label: string;
  align?: 'start' | 'end';
}

/**
 * The row-level actions dropdown.
 *
 * Declaring items as data rather than JSX is what lets a list compute which
 * actions apply to each row without every screen rebuilding the same menu.
 */
export function ActionMenu({ items, label, align = 'end' }: ActionMenuProps): React.JSX.Element {
  const visible = items.filter((item) => item.hidden !== true);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={label}
          // The trigger really is inside the row, so its click would otherwise
          // bubble and navigate. (The menu's *items* are handled in DataTable,
          // which cannot rely on propagation because React re-parents portal
          // events through the component tree.)
          onClick={(event) => {
            event.stopPropagation();
          }}
        >
          <MoreHorizontal className="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align={align}>
        {visible.map((item) => {
          const Icon = item.icon;
          const content = (
            <>
              {Icon ? <Icon aria-hidden="true" /> : null}
              {item.label}
            </>
          );

          return (
            <React.Fragment key={item.id}>
              {item.separatorBefore === true ? <DropdownMenuSeparator /> : null}
              <DropdownMenuItem
                variant={item.destructive === true ? 'destructive' : 'default'}
                disabled={item.disabled}
                {...(item.href === undefined ? { onSelect: item.onSelect } : { asChild: true as const })}
              >
                {item.href === undefined ? content : <Link href={item.href}>{content}</Link>}
              </DropdownMenuItem>
            </React.Fragment>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

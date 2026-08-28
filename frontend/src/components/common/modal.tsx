'use client';

import * as React from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  /** Replaces the default Cancel/Confirm pair when supplied. */
  footer?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  isConfirming?: boolean;
  confirmVariant?: React.ComponentProps<typeof Button>['variant'];
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

const sizeClass: Record<NonNullable<ModalProps['size']>, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

/**
 * The standard modal used across the product.
 *
 * Wrapping the Radix dialog here means every modal gets the same footer layout,
 * button order and loading behaviour without each screen rebuilding it.
 */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  isConfirming = false,
  confirmVariant = 'default',
  size = 'md',
  className,
}: ModalProps): React.JSX.Element {
  const showDefaultFooter = footer === undefined && typeof onConfirm === 'function';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(sizeClass[size], className)}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>

        {children}

        {footer ?? null}

        {showDefaultFooter ? (
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
              }}
              disabled={isConfirming}
            >
              {cancelLabel}
            </Button>
            <Button variant={confirmVariant} onClick={onConfirm} isLoading={isConfirming}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void;
  isConfirming?: boolean;
  /** Use for irreversible actions -- renders the confirm button in red. */
  destructive?: boolean;
}

/** A modal preset for "are you sure?" confirmations. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  onConfirm,
  isConfirming = false,
  destructive = false,
}: ConfirmDialogProps): React.JSX.Element {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      confirmLabel={confirmLabel}
      onConfirm={onConfirm}
      isConfirming={isConfirming}
      confirmVariant={destructive ? 'destructive' : 'default'}
    />
  );
}

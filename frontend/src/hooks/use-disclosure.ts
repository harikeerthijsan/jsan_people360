'use client';

import * as React from 'react';

export interface Disclosure {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  setOpen: (open: boolean) => void;
}

/** Boolean open/close state for modals, drawers and disclosure widgets. */
export function useDisclosure(initial = false): Disclosure {
  const [isOpen, setIsOpen] = React.useState(initial);

  const open = React.useCallback(() => {
    setIsOpen(true);
  }, []);

  const close = React.useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggle = React.useCallback(() => {
    setIsOpen((previous) => !previous);
  }, []);

  return React.useMemo(
    () => ({ isOpen, open, close, toggle, setOpen: setIsOpen }),
    [isOpen, open, close, toggle],
  );
}

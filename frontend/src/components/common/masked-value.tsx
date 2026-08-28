'use client';

import { Eye, EyeOff, Loader2 } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * A sensitive value with an explicit reveal.
 *
 * The masked form is what the server sent; the unmasked form arrives only when
 * the reader asks for it, and asking is audited. That is why revealing is a
 * button rather than a hover: a hover is something a mouse does, not something
 * a person decides.
 */

interface MaskedValueProps {
  /** The masked value, as returned by the API. Never derived on the client. */
  masked: string | null;
  /** The full value, once fetched. `undefined` while it has not been. */
  revealed?: string | null;
  /** Whether the reader has asked to see it. */
  isRevealed: boolean;
  /** Called when the reveal is toggled. */
  onToggle: () => void;
  /** True while the unmasked value is in flight. */
  isLoading?: boolean;
  /** Names the value for assistive technology, e.g. "Aadhaar number". */
  label: string;
  className?: string;
}

export function MaskedValue({
  masked,
  revealed,
  isRevealed,
  onToggle,
  isLoading = false,
  label,
  className,
}: MaskedValueProps): React.JSX.Element {
  if (masked === null) {
    return <span className="text-muted-foreground">—</span>;
  }

  const showing = isRevealed && typeof revealed === 'string';

  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className="font-mono text-sm tabular-nums">{showing ? revealed : masked}</span>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-6"
        onClick={onToggle}
        disabled={isLoading}
        aria-label={showing ? `Hide ${label}` : `Reveal ${label}`}
        aria-pressed={showing}
      >
        {isLoading ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : showing ? (
          <EyeOff className="size-3.5" aria-hidden="true" />
        ) : (
          <Eye className="size-3.5" aria-hidden="true" />
        )}
      </Button>
    </span>
  );
}

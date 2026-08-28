'use client';
import * as React from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
export function RichTextEditor({
  id,
  value,
  onChange,
  disabled,
  className,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}): React.JSX.Element {
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (ref.current && ref.current.innerHTML !== value) ref.current.innerHTML = value;
  }, [value]);
  const command = (name: string) => {
    ref.current?.focus();
    document.execCommand(name);
    onChange(ref.current?.innerHTML ?? '');
  };
  return (
    <div className={cn('rounded-md border', className)}>
      <div className="flex gap-1 border-b p-1">
        <Button type="button" variant="ghost" size="sm" onClick={() => command('bold')} disabled={disabled}>
          Bold
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => command('insertUnorderedList')}
          disabled={disabled}
        >
          List
        </Button>
      </div>
      <div
        ref={ref}
        id={id}
        role="textbox"
        aria-multiline="true"
        contentEditable={!disabled}
        suppressContentEditableWarning
        className="min-h-32 p-3 text-sm outline-none"
        onInput={(e) => onChange(e.currentTarget.innerHTML)}
      />
    </div>
  );
}

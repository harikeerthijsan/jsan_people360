import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge conditional class names, resolving conflicting Tailwind utilities so the
 * last one wins. This is what lets every component accept a `className` prop
 * that can genuinely override its defaults.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Initials for an avatar fallback: "Jane Doe" -> "JD". */
export function getInitials(fullName: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  const first = words[0]?.charAt(0) ?? '';
  const last = words.length > 1 ? (words[words.length - 1]?.charAt(0) ?? '') : '';
  return (first + last).toUpperCase();
}

/** Format an ISO timestamp for display, tolerating malformed input. */
export function formatDate(
  value: string | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' },
): string {
  if (!value) return '—';
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('en-GB', options).format(date);
}

/** Format an ISO timestamp including the time of day. */
export function formatDateTime(value: string | Date | null | undefined): string {
  return formatDate(value, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Convert a route segment into a readable label: "audit-logs" -> "Audit Logs". */
export function humanizeSegment(segment: string): string {
  return segment.replace(/[-_]/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

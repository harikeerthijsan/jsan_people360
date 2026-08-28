import { cn, formatDate, getInitials, humanizeSegment } from '@/lib/utils';

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1');
  });

  it('lets a later conflicting utility win, so className can override defaults', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4');
  });

  it('drops falsy values', () => {
    expect(cn('px-2', false, undefined, null, 'py-1')).toBe('px-2 py-1');
  });
});

describe('getInitials', () => {
  it.each([
    ['Jane Doe', 'JD'],
    ['jane van der Berg', 'JB'],
    ['Madonna', 'M'],
    ['  spaced   out  ', 'SO'],
    ['', '?'],
  ])('turns %s into %s', (input, expected) => {
    expect(getInitials(input)).toBe(expected);
  });
});

describe('formatDate', () => {
  it('formats an ISO timestamp', () => {
    expect(formatDate('2026-03-15T10:30:00Z')).toBe('15 Mar 2026');
  });

  it('renders a dash for missing values', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
  });

  it('renders a dash rather than "Invalid Date" for malformed input', () => {
    expect(formatDate('not-a-date')).toBe('—');
  });
});

describe('humanizeSegment', () => {
  it.each([
    ['audit-logs', 'Audit Logs'],
    ['reset_password', 'Reset Password'],
    ['dashboard', 'Dashboard'],
  ])('turns %s into %s', (input, expected) => {
    expect(humanizeSegment(input)).toBe(expected);
  });
});

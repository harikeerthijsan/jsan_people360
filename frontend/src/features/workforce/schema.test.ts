import {
  holidayCalendarSchema,
  leaveApplySchema,
  leaveTypeSchema,
  shiftSchema,
  timesheetSchema,
} from './schema';

/**
 * The client-side rules worth defending.
 *
 * Each of these mirrors a server rule, and each is one a later edit could
 * silently relax -- leaving the user to discover the problem only after a round
 * trip, which is exactly what mirroring was meant to avoid.
 */

const id = '11111111-1111-4111-8111-111111111111';

describe('shiftSchema', () => {
  const valid = {
    name: 'General',
    code: 'GEN',
    shift_type: 'general' as const,
    start_time: '09:30',
    end_time: '18:30',
    grace_minutes: 15,
    break_minutes: 60,
    weekly_off: [5, 6],
    status: 'active' as const,
  };

  it('accepts a normal shift', () => {
    expect(shiftSchema.safeParse(valid).success).toBe(true);
  });

  it('accepts a night shift that ends before it starts', () => {
    const result = shiftSchema.safeParse({ ...valid, start_time: '22:00', end_time: '06:30' });
    expect(result.success).toBe(true);
  });

  it('refuses a shift of zero length', () => {
    const result = shiftSchema.safeParse({ ...valid, start_time: '09:30', end_time: '09:30' });
    expect(result.success).toBe(false);
  });

  it('refuses a shift with every day off', () => {
    const result = shiftSchema.safeParse({ ...valid, weekly_off: [0, 1, 2, 3, 4, 5, 6] });
    expect(result.success).toBe(false);
  });

  it('refuses the same day listed twice', () => {
    const result = shiftSchema.safeParse({ ...valid, weekly_off: [5, 5] });
    expect(result.success).toBe(false);
  });
});

describe('leaveTypeSchema', () => {
  const valid = {
    name: 'Casual Leave',
    code: 'CL',
    description: '',
    annual_allocation: '12',
    carry_forward: false,
    max_carry_forward: '0',
    allows_negative: false,
    is_paid: true,
    requires_document: false,
    status: 'active' as const,
  };

  it('accepts a type that does not carry forward', () => {
    expect(leaveTypeSchema.safeParse(valid).success).toBe(true);
  });

  it('refuses a maximum carry forward when carry forward is off', () => {
    const result = leaveTypeSchema.safeParse({ ...valid, max_carry_forward: '5' });
    expect(result.success).toBe(false);
  });

  it('refuses carry forward without a maximum', () => {
    const result = leaveTypeSchema.safeParse({ ...valid, carry_forward: true });
    expect(result.success).toBe(false);
  });
});

describe('leaveApplySchema', () => {
  const valid = {
    leave_type_id: id,
    from_date: '2026-08-10',
    to_date: '2026-08-12',
    day_part: 'full_day' as const,
    reason: 'Family function',
    supporting_document_id: '',
  };

  it('accepts a multi-day full-day request', () => {
    expect(leaveApplySchema.safeParse(valid).success).toBe(true);
  });

  it('refuses leave that ends before it starts', () => {
    const result = leaveApplySchema.safeParse({ ...valid, to_date: '2026-08-09' });
    expect(result.success).toBe(false);
  });

  it('refuses a half day spanning more than one date', () => {
    const result = leaveApplySchema.safeParse({ ...valid, day_part: 'first_half' });
    expect(result.success).toBe(false);
  });

  it('accepts a half day on a single date', () => {
    const result = leaveApplySchema.safeParse({
      ...valid,
      day_part: 'first_half',
      to_date: valid.from_date,
    });
    expect(result.success).toBe(true);
  });
});

describe('holidayCalendarSchema', () => {
  const valid = {
    name: 'India 2026',
    year: 2026,
    location_id: '',
    description: '',
    holidays: [{ name: 'Republic Day', holiday_date: '2026-01-26', holiday_type: 'public' as const }],
  };

  it('accepts a calendar with one holiday', () => {
    expect(holidayCalendarSchema.safeParse(valid).success).toBe(true);
  });

  it('refuses the same date twice', () => {
    const result = holidayCalendarSchema.safeParse({
      ...valid,
      holidays: [valid.holidays[0], { ...valid.holidays[0], name: 'Another' }],
    });
    expect(result.success).toBe(false);
  });

  // The server's check constraint accepts exactly these three. A value the form
  // offers but the database rejects is unfixable from the UI, so the list is
  // asserted rather than assumed.
  it.each(['public', 'restricted', 'optional'] as const)('accepts the %s holiday type', (type) => {
    const result = holidayCalendarSchema.safeParse({
      ...valid,
      holidays: [{ ...valid.holidays[0], holiday_type: type }],
    });
    expect(result.success).toBe(true);
  });

  it('refuses a holiday type the server does not accept', () => {
    const result = holidayCalendarSchema.safeParse({
      ...valid,
      holidays: [{ ...valid.holidays[0], holiday_type: 'company' }],
    });
    expect(result.success).toBe(false);
  });

  it('refuses a date outside the year', () => {
    const result = holidayCalendarSchema.safeParse({
      ...valid,
      holidays: [{ ...valid.holidays[0], holiday_date: '2025-01-26' }],
    });
    expect(result.success).toBe(false);
  });
});

describe('timesheetSchema', () => {
  // 2026-08-10 is a Monday.
  const monday = '2026-08-10';
  const entry = {
    project_id: id,
    work_date: monday,
    task: 'Order service',
    hours: '8.00',
    billable: true,
    comments: '',
  };

  it('accepts a week that starts on a Monday', () => {
    const result = timesheetSchema.safeParse({ week_start_date: monday, entries: [entry] });
    expect(result.success).toBe(true);
  });

  it('refuses a week that starts on any other day', () => {
    const result = timesheetSchema.safeParse({ week_start_date: '2026-08-11', entries: [] });
    expect(result.success).toBe(false);
  });

  it('refuses more than twenty-four hours on one day', () => {
    const result = timesheetSchema.safeParse({
      week_start_date: monday,
      entries: [
        { ...entry, hours: '13.00' },
        { ...entry, task: 'Review', hours: '12.00' },
      ],
    });
    expect(result.success).toBe(false);
  });

  it('refuses the same project and task twice on a day', () => {
    const result = timesheetSchema.safeParse({
      week_start_date: monday,
      entries: [entry, { ...entry, hours: '2.00' }],
    });
    expect(result.success).toBe(false);
  });

  it('accepts the same task on two different days', () => {
    const result = timesheetSchema.safeParse({
      week_start_date: monday,
      entries: [entry, { ...entry, work_date: '2026-08-11' }],
    });
    expect(result.success).toBe(true);
  });

  it('refuses an entry outside the week', () => {
    const result = timesheetSchema.safeParse({
      week_start_date: monday,
      entries: [{ ...entry, work_date: '2026-08-18' }],
    });
    expect(result.success).toBe(false);
  });
});

import {
  myAddressSchema,
  myDocumentUploadSchema,
  myLeaveApplySchema,
  myProfileSchema,
  myRegularizationSchema,
  myTimesheetSchema,
} from './schema';

/**
 * The portal's client-side rules.
 *
 * Two kinds of test here. Most mirror a server rule, and exist because a later
 * edit could silently relax one -- leaving the user to find out only after a
 * round trip, which is what mirroring was meant to avoid.
 *
 * The profile tests are the other kind. They assert what the form *cannot*
 * carry, which is the whole security property of the profile screen: an
 * employee changes how to reach them and nothing about their employment.
 */

const id = '11111111-1111-4111-8111-111111111111';

describe('myProfileSchema', () => {
  it('accepts the fields an employee owns', () => {
    const result = myProfileSchema.safeParse({
      personal_email: 'Person@Example.com',
      mobile_number: '+91 90000 00001',
      emergency_contact_name: 'Next Of Kin',
      emergency_contact_number: '+91 90000 00002',
      emergency_contact_relationship: 'Sibling',
    });

    expect(result.success).toBe(true);
    // Normalised on the way through, so two spellings of one address cannot
    // both be stored.
    expect(result.success && result.data.personal_email).toBe('person@example.com');
  });

  it('treats a blank field as unset rather than as an empty string', () => {
    const result = myProfileSchema.safeParse({ personal_email: '', mobile_number: '' });
    expect(result.success).toBe(true);
    expect(result.success && result.data.personal_email).toBeNull();
    expect(result.success && result.data.mobile_number).toBeNull();
  });

  it('refuses an address that is not an address', () => {
    expect(myProfileSchema.safeParse({ personal_email: 'not-an-email' }).success).toBe(false);
  });

  it.each([
    'team_id',
    'designation_id',
    'grade_id',
    'reporting_manager_id',
    'employment_status',
    'joining_date',
    'official_email',
    'employee_code',
    'ctc',
  ])('drops %s, which is not an employee field to set', (field) => {
    const result = myProfileSchema.safeParse({ mobile_number: '+91 90000 00001', [field]: 'anything' });

    expect(result.success).toBe(true);
    // Not merely rejected on the server: it never leaves the browser, because
    // the parsed value has no such key to send.
    expect(result.success && Object.keys(result.data)).not.toContain(field);
  });
});

describe('myLeaveApplySchema', () => {
  const valid = {
    leave_type_id: id,
    from_date: '2026-09-01',
    to_date: '2026-09-03',
    day_part: 'full_day' as const,
    reason: 'Family event',
  };

  it('accepts a multi-day request', () => {
    expect(myLeaveApplySchema.safeParse(valid).success).toBe(true);
  });

  it('refuses leave that ends before it starts', () => {
    expect(myLeaveApplySchema.safeParse({ ...valid, to_date: '2026-08-30' }).success).toBe(false);
  });

  it('refuses a half day spread over several dates', () => {
    const result = myLeaveApplySchema.safeParse({ ...valid, day_part: 'first_half' });
    expect(result.success).toBe(false);
  });

  it('accepts a half day on a single date', () => {
    const result = myLeaveApplySchema.safeParse({
      ...valid,
      day_part: 'first_half',
      to_date: valid.from_date,
    });
    expect(result.success).toBe(true);
  });
});

describe('myRegularizationSchema', () => {
  const valid = {
    attendance_date: '2026-08-10',
    requested_check_in_at: '2026-08-10T09:00',
    requested_check_out_at: '2026-08-10T18:00',
    reason: 'Forgot to check in',
  };

  it('accepts a correction with both times', () => {
    expect(myRegularizationSchema.safeParse(valid).success).toBe(true);
  });

  it('accepts a correction with only one of them', () => {
    const result = myRegularizationSchema.safeParse({
      ...valid,
      requested_check_out_at: undefined,
    });
    expect(result.success).toBe(true);
  });

  it('refuses a correction that corrects nothing', () => {
    const result = myRegularizationSchema.safeParse({
      ...valid,
      requested_check_in_at: undefined,
      requested_check_out_at: undefined,
    });
    expect(result.success).toBe(false);
  });

  it('refuses a check-out before the check-in', () => {
    const result = myRegularizationSchema.safeParse({
      ...valid,
      requested_check_out_at: '2026-08-10T08:00',
    });
    expect(result.success).toBe(false);
  });
});

describe('myTimesheetSchema', () => {
  const entry = {
    project_id: id,
    work_date: '2026-08-10',
    task: 'Implementation',
    hours: '8.00',
    billable: true,
  };
  const valid = { week_start_date: '2026-08-10', entries: [entry] };

  it('accepts a normal week', () => {
    expect(myTimesheetSchema.safeParse(valid).success).toBe(true);
  });

  it('refuses a day totalling more than twenty-four hours', () => {
    const result = myTimesheetSchema.safeParse({
      ...valid,
      entries: [entry, { ...entry, task: 'Review', hours: '20.00' }],
    });
    expect(result.success).toBe(false);
  });

  it('refuses the same project and task twice on one day', () => {
    const result = myTimesheetSchema.safeParse({ ...valid, entries: [entry, { ...entry, hours: '2.00' }] });
    expect(result.success).toBe(false);
  });

  it('accepts the same task on two different days', () => {
    const result = myTimesheetSchema.safeParse({
      ...valid,
      entries: [entry, { ...entry, work_date: '2026-08-11' }],
    });
    expect(result.success).toBe(true);
  });

  it('refuses a date outside the week', () => {
    const result = myTimesheetSchema.safeParse({
      ...valid,
      entries: [{ ...entry, work_date: '2026-08-20' }],
    });
    expect(result.success).toBe(false);
  });

  it('refuses zero hours, which is a row nobody meant to add', () => {
    expect(myTimesheetSchema.safeParse({ ...valid, entries: [{ ...entry, hours: '0' }] }).success).toBe(
      false,
    );
  });
});

describe('myAddressSchema', () => {
  const valid = {
    address_type: 'current' as const,
    address_line1: '12 Residency Road',
    city: 'Hyderabad',
    state: 'Telangana',
    country: 'India',
    postal_code: '500081',
  };

  it('accepts a complete address', () => {
    expect(myAddressSchema.safeParse(valid).success).toBe(true);
  });

  it('refuses an address with no first line', () => {
    expect(myAddressSchema.safeParse({ ...valid, address_line1: '' }).success).toBe(false);
  });

  it('refuses an address type the employee does not own', () => {
    expect(myAddressSchema.safeParse({ ...valid, address_type: 'office' }).success).toBe(false);
  });
});

describe('myDocumentUploadSchema', () => {
  it('accepts a named document with a type', () => {
    const result = myDocumentUploadSchema.safeParse({ name: 'Passport', document_type_id: id });
    expect(result.success).toBe(true);
  });

  it('refuses an upload with no type chosen', () => {
    expect(myDocumentUploadSchema.safeParse({ name: 'Passport', document_type_id: '' }).success).toBe(false);
  });

  it('has no owner field to send', () => {
    const result = myDocumentUploadSchema.safeParse({
      name: 'Passport',
      document_type_id: id,
      owner_id: 'somebody-else',
    });

    expect(result.success).toBe(true);
    expect(result.success && Object.keys(result.data)).not.toContain('owner_id');
  });
});

import {
  aadhaarSchema,
  accountNumberSchema,
  createEmployeeSchema,
  ctcSchema,
  ifscSchema,
  joiningDateSchema,
  panSchema,
  postalCodeSchema,
  promoteEmployeeSchema,
  uanSchema,
} from '@/features/employees/schemas/employee.schemas';

const VALID_UUID = '0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f';

function createPayload(overrides: Record<string, unknown> = {}) {
  return {
    first_name: 'Priya',
    last_name: 'Sharma',
    official_email: 'priya.sharma@jsan.example',
    joining_date: '2026-01-15',
    employment_status: 'probation',
    ...overrides,
  };
}

describe('aadhaarSchema', () => {
  it('strips the separators people type', () => {
    expect(aadhaarSchema.parse('2345 6789 0123')).toBe('234567890123');
    expect(aadhaarSchema.parse('2345-6789-0123')).toBe('234567890123');
  });

  it.each([
    ['1234567890123', 'thirteen digits'],
    ['034567890123', 'starts with zero'],
    ['134567890123', 'starts with one'],
    ['23456789012A', 'contains a letter'],
  ])('rejects %s (%s)', (value) => {
    expect(aadhaarSchema.safeParse(value).success).toBe(false);
  });

  it('treats blank as absent so the field can be cleared', () => {
    const result = aadhaarSchema.safeParse('');
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).toBeNull();
  });
});

describe('panSchema', () => {
  it('upper-cases the value', () => {
    expect(panSchema.parse('abcde1234f')).toBe('ABCDE1234F');
  });

  it.each(['ABCD1234F', 'ABCDE12345', '1BCDE1234F'])('rejects %s', (value) => {
    expect(panSchema.safeParse(value).success).toBe(false);
  });
});

describe('ifscSchema', () => {
  it('upper-cases the value', () => {
    expect(ifscSchema.parse('hdfc0001234')).toBe('HDFC0001234');
  });

  it('requires a zero in the fifth position', () => {
    expect(ifscSchema.safeParse('HDFC1001234').success).toBe(false);
  });
});

describe('uanSchema', () => {
  it('accepts exactly twelve digits', () => {
    expect(uanSchema.parse('100 200 300 400')).toBe('100200300400');
  });

  it('rejects a short value', () => {
    expect(uanSchema.safeParse('12345').success).toBe(false);
  });
});

describe('accountNumberSchema', () => {
  it('strips the spaces people type', () => {
    expect(accountNumberSchema.parse('5010 0123 4567 89')).toBe('50100123456789');
  });

  it('rejects punctuation', () => {
    expect(accountNumberSchema.safeParse('5010/0123').success).toBe(false);
  });
});

describe('postalCodeSchema', () => {
  it.each(['500081', 'SW1A 1AA', 'K1A-0B1'])('accepts %s', (value) => {
    expect(postalCodeSchema.safeParse(value).success).toBe(true);
  });

  it('rejects a single character', () => {
    expect(postalCodeSchema.safeParse('5').success).toBe(false);
  });
});

describe('ctcSchema', () => {
  it('strips grouping separators', () => {
    expect(ctcSchema.parse('14,50,000')).toBe('1450000');
  });

  it('keeps two decimal places', () => {
    expect(ctcSchema.parse('1450000.50')).toBe('1450000.50');
  });

  it('rejects more than two decimal places', () => {
    expect(ctcSchema.safeParse('1450000.505').success).toBe(false);
  });

  it('treats blank as absent', () => {
    const result = ctcSchema.safeParse('');
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).toBeNull();
  });
});

describe('joiningDateSchema', () => {
  it('is required', () => {
    expect(joiningDateSchema.safeParse('').success).toBe(false);
  });

  it('allows a date shortly in the future', () => {
    /* Pre-boarding someone before their start date is the normal case. */
    const soon = new Date();
    soon.setMonth(soon.getMonth() + 1);
    expect(joiningDateSchema.safeParse(soon.toISOString().slice(0, 10)).success).toBe(true);
  });

  it('rejects a date more than a year out', () => {
    const far = new Date();
    far.setFullYear(far.getFullYear() + 2);
    expect(joiningDateSchema.safeParse(far.toISOString().slice(0, 10)).success).toBe(false);
  });
});

describe('createEmployeeSchema', () => {
  it('accepts a minimal payload', () => {
    expect(createEmployeeSchema.safeParse(createPayload()).success).toBe(true);
  });

  it('normalises the identifiers', () => {
    const result = createEmployeeSchema.parse(
      createPayload({
        first_name: '  Priya  ',
        last_name: 'Van   Sharma',
        official_email: ' Priya@JSAN.EXAMPLE ',
      }),
    );

    expect(result.first_name).toBe('Priya');
    expect(result.last_name).toBe('Van Sharma');
    expect(result.official_email).toBe('priya@jsan.example');
  });

  it('requires an official email', () => {
    expect(createEmployeeSchema.safeParse(createPayload({ official_email: '' })).success).toBe(false);
  });

  it('sends a cleared optional field as an explicit null', () => {
    const result = createEmployeeSchema.parse(createPayload({ nationality: '', mobile_number: '' }));

    expect(JSON.parse(JSON.stringify(result))).toMatchObject({
      nationality: null,
      mobile_number: null,
    });
  });

  it('treats organizational references as optional', () => {
    const result = createEmployeeSchema.safeParse(createPayload());
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.team_id).toBeNull();
  });

  it('rejects a malformed organizational reference', () => {
    expect(createEmployeeSchema.safeParse(createPayload({ team_id: 'nope' })).success).toBe(false);
  });
});

describe('promoteEmployeeSchema', () => {
  const base = { effective_date: '2026-06-01', reason: '', notes: '' };

  it('rejects a promotion that changes nothing', () => {
    /* A history row with no content reads as though something happened. */
    expect(promoteEmployeeSchema.safeParse(base).success).toBe(false);
  });

  it('accepts a CTC-only promotion', () => {
    expect(promoteEmployeeSchema.safeParse({ ...base, ctc: '1750000' }).success).toBe(true);
  });

  it('accepts a designation-only promotion', () => {
    expect(promoteEmployeeSchema.safeParse({ ...base, designation_id: VALID_UUID }).success).toBe(true);
  });
});

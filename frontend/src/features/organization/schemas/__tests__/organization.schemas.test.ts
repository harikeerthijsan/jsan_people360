import {
  businessUnitSchema,
  designationSchema,
  gradeSchema,
  locationSchema,
  masterCodeSchema,
  masterNameSchema,
  organizationSchema,
  teamSchema,
} from '@/features/organization/schemas/organization.schemas';

const VALID_UUID = '0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f';

describe('masterNameSchema', () => {
  it('trims surrounding whitespace', () => {
    expect(masterNameSchema.parse('  Technology  ')).toBe('Technology');
  });

  it('collapses internal whitespace runs', () => {
    expect(masterNameSchema.parse('Web   Development')).toBe('Web Development');
  });

  it('rejects a name shorter than two characters', () => {
    expect(masterNameSchema.safeParse('A').success).toBe(false);
  });

  it('rejects a blank name once trimmed', () => {
    expect(masterNameSchema.safeParse('    ').success).toBe(false);
  });
});

describe('masterCodeSchema', () => {
  it('upper-cases the code', () => {
    expect(masterCodeSchema.parse('tech')).toBe('TECH');
  });

  it('replaces internal spaces with underscores', () => {
    expect(masterCodeSchema.parse('full time')).toBe('FULL_TIME');
  });

  it('accepts hyphens and underscores', () => {
    expect(masterCodeSchema.parse('tech-01_a')).toBe('TECH-01_A');
  });

  it.each(['-LEAD', '_LEAD', 'HAS.DOT', 'HAS/SLASH'])('rejects %s', (code) => {
    expect(masterCodeSchema.safeParse(code).success).toBe(false);
  });
});

describe('businessUnitSchema', () => {
  it('accepts a complete payload', () => {
    const result = businessUnitSchema.safeParse({
      name: 'Technology',
      code: 'TECH',
      description: '',
      status: 'active',
    });

    expect(result.success).toBe(true);
    if (result.success) {
      // Explicitly `null`, never `undefined`: JSON.stringify drops undefined
      // properties, so an omitted key would leave the column unchanged and the
      // user could never clear a field they had already filled in.
      expect(result.data.description).toBeNull();
    }
  });

  it('serialises a cleared description as an explicit null', () => {
    const result = businessUnitSchema.parse({
      name: 'Technology',
      code: 'TECH',
      description: '',
      status: 'active',
    });

    expect(JSON.parse(JSON.stringify(result))).toHaveProperty('description', null);
  });

  it('requires a status', () => {
    expect(businessUnitSchema.safeParse({ name: 'Technology', code: 'TECH' }).success).toBe(false);
  });

  it('rejects an unknown status', () => {
    const result = businessUnitSchema.safeParse({
      name: 'Technology',
      code: 'TECH',
      status: 'retired',
    });
    expect(result.success).toBe(false);
  });
});

describe('designationSchema parent', () => {
  const base = { name: 'Cloud Engineer', code: 'CLOUD', status: 'active', level: 2 };

  it('requires a business unit', () => {
    const result = designationSchema.safeParse(base);
    expect(result.success).toBe(false);
  });

  it('rejects a business unit that is not a uuid', () => {
    const result = designationSchema.safeParse({ ...base, business_unit_id: 'not-a-uuid' });
    expect(result.success).toBe(false);
  });

  it('accepts a valid selection', () => {
    const result = designationSchema.safeParse({ ...base, business_unit_id: VALID_UUID });
    expect(result.success).toBe(true);
  });
});

describe('teamSchema', () => {
  const base = { name: 'Platform', status: 'active', business_unit_id: VALID_UUID };

  it('sends an unselected manager as null so the server unassigns it', () => {
    const result = teamSchema.safeParse({ ...base, manager_id: '' });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.manager_id).toBeNull();
    }
  });

  it('accepts a selected manager', () => {
    const result = teamSchema.safeParse({ ...base, manager_id: VALID_UUID });
    expect(result.success).toBe(true);
  });

  it('rejects a malformed manager id', () => {
    expect(teamSchema.safeParse({ ...base, manager_id: 'nope' }).success).toBe(false);
  });
});

describe('level validation', () => {
  const base = { name: 'Engineer', code: 'ENG', status: 'active', business_unit_id: VALID_UUID };

  it('rejects a level below one', () => {
    expect(designationSchema.safeParse({ ...base, level: 0 }).success).toBe(false);
  });

  it('rejects a fractional level', () => {
    expect(designationSchema.safeParse({ ...base, level: 1.5 }).success).toBe(false);
  });

  it('rejects a missing level', () => {
    expect(designationSchema.safeParse(base).success).toBe(false);
  });

  it('accepts a valid level', () => {
    expect(designationSchema.safeParse({ ...base, level: 3 }).success).toBe(true);
  });

  it('applies the same rule to grades', () => {
    expect(gradeSchema.safeParse({ name: 'Band 1', code: 'G1', status: 'active', level: 1 }).success).toBe(
      true,
    );
    expect(gradeSchema.safeParse({ name: 'Band 1', code: 'G1', status: 'active', level: 0 }).success).toBe(
      false,
    );
  });
});

describe('locationSchema', () => {
  const base = {
    name: 'Hyderabad HQ',
    code: 'HYD',
    status: 'active',
    country: 'India',
    state: 'Telangana',
    city: 'Hyderabad',
    address: 'Plot 12, HITEC City',
    timezone: 'Asia/Kolkata',
  };

  it('accepts a complete location', () => {
    expect(locationSchema.safeParse(base).success).toBe(true);
  });

  it('rejects an unsupported time zone', () => {
    expect(locationSchema.safeParse({ ...base, timezone: 'Mars/Olympus' }).success).toBe(false);
  });

  it('rejects an address that is too short', () => {
    expect(locationSchema.safeParse({ ...base, address: 'abc' }).success).toBe(false);
  });

  it('collapses whitespace in place names', () => {
    const result = locationSchema.safeParse({ ...base, city: '  New   Delhi ' });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.city).toBe('New Delhi');
    }
  });
});

describe('organizationSchema', () => {
  const base = {
    name: 'JSAN Technologies',
    status: 'active',
    legal_name: 'JSAN Technologies Private Limited',
    registration_number: 'U72900TG2015PTC098765',
    timezone: 'Asia/Kolkata',
    currency: 'INR',
    address_line1: 'Plot 12, HITEC City',
    city: 'Hyderabad',
    state: 'Telangana',
    country: 'India',
  };

  it('accepts a complete profile', () => {
    expect(organizationSchema.safeParse(base).success).toBe(true);
  });

  it('upper-cases the currency', () => {
    const result = organizationSchema.safeParse({ ...base, currency: 'inr' });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.currency).toBe('INR');
    }
  });

  it('sends a blank GST number as null so it can be cleared', () => {
    const result = organizationSchema.safeParse({ ...base, gst_number: '  ' });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.gst_number).toBeNull();
    }
  });

  it('sends every optional field as null when blank, so none is silently skipped', () => {
    const result = organizationSchema.parse({
      ...base,
      gst_number: '',
      pan_number: '',
      website: '',
      logo_url: '',
      address_line2: '',
      postal_code: '',
      description: '',
    });

    const payload = JSON.parse(JSON.stringify(result)) as Record<string, unknown>;
    for (const field of [
      'gst_number',
      'pan_number',
      'website',
      'logo_url',
      'address_line2',
      'postal_code',
      'description',
    ]) {
      expect(payload).toHaveProperty(field, null);
    }
  });

  it('rejects a malformed PAN', () => {
    expect(organizationSchema.safeParse({ ...base, pan_number: 'ABCD12345' }).success).toBe(false);
  });

  it('upper-cases a valid PAN', () => {
    const result = organizationSchema.safeParse({ ...base, pan_number: 'aabcj1234m' });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.pan_number).toBe('AABCJ1234M');
    }
  });

  it('rejects a malformed GSTIN', () => {
    expect(organizationSchema.safeParse({ ...base, gst_number: '36AABCJ' }).success).toBe(false);
  });

  it('rejects a website that is not a url', () => {
    expect(organizationSchema.safeParse({ ...base, website: 'jsan dot com' }).success).toBe(false);
  });

  it('rejects a website without a supported scheme', () => {
    expect(organizationSchema.safeParse({ ...base, website: 'ftp://jsan.example' }).success).toBe(false);
  });

  it('accepts an https website', () => {
    expect(organizationSchema.safeParse({ ...base, website: 'https://jsan.example' }).success).toBe(true);
  });
});

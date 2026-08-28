import {
  changeOwnPasswordSchema,
  createUserSchema,
  editUserSchema,
  mobileSchema,
  passwordSchema,
  profileSchema,
  resetPasswordSchema,
  usernameSchema,
} from '@/features/users/schemas/user.schemas';

const VALID_UUID = '0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f';

function createPayload(overrides: Record<string, unknown> = {}) {
  return {
    first_name: 'Jane',
    last_name: 'Doe',
    username: 'jane.doe',
    email: 'jane.doe@example.com',
    status: 'active',
    password: 'Str0ng@1',
    force_password_change: false,
    ...overrides,
  };
}

describe('passwordSchema', () => {
  it('accepts an eight-character password meeting every rule', () => {
    expect(passwordSchema.safeParse('Str0ng@1').success).toBe(true);
  });

  it.each([
    ['Sh0rt@a', 'shorter than eight'],
    ['alllower@1', 'no uppercase'],
    ['ALLUPPER@1', 'no lowercase'],
    ['NoDigits@x', 'no digit'],
    ['NoSpecial1x', 'no special character'],
  ])('rejects %s (%s)', (password) => {
    expect(passwordSchema.safeParse(password).success).toBe(false);
  });
});

describe('usernameSchema', () => {
  it('lower-cases the value', () => {
    expect(usernameSchema.parse('Jane.Doe')).toBe('jane.doe');
  });

  it('turns spaces into dots', () => {
    expect(usernameSchema.parse('jane doe')).toBe('jane.doe');
  });

  it.each(['.leading', '-leading', 'has@at', 'has/slash', 'ab'])('rejects %s', (username) => {
    expect(usernameSchema.safeParse(username).success).toBe(false);
  });
});

describe('mobileSchema', () => {
  it.each(['+91 98765 43210', '9876543210', '020 7946 0958', '+1 (555) 123-4567'])('accepts %s', (number) => {
    expect(mobileSchema.safeParse(number).success).toBe(true);
  });

  it.each(['call me', '12', 'phone: 999'])('rejects %s', (number) => {
    expect(mobileSchema.safeParse(number).success).toBe(false);
  });

  it('sends a blank number as null so it can be cleared', () => {
    const result = mobileSchema.safeParse('   ');
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).toBeNull();
  });
});

describe('createUserSchema', () => {
  it('accepts a complete payload', () => {
    expect(createUserSchema.safeParse(createPayload()).success).toBe(true);
  });

  it('normalises the identifiers', () => {
    const result = createUserSchema.parse(
      createPayload({ first_name: '  Jane  ', last_name: 'Van   Doe', email: ' Jane@EXAMPLE.com ' }),
    );

    expect(result.first_name).toBe('Jane');
    expect(result.last_name).toBe('Van Doe');
    expect(result.email).toBe('jane@example.com');
  });

  it('requires a password', () => {
    const { password: _password, ...withoutPassword } = createPayload();
    expect(createUserSchema.safeParse(withoutPassword).success).toBe(false);
  });

  it('treats organizational references as optional', () => {
    const result = createUserSchema.safeParse(createPayload());
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.business_unit_id).toBeNull();
  });

  it('accepts a valid organizational reference', () => {
    const result = createUserSchema.safeParse(createPayload({ business_unit_id: VALID_UUID }));
    expect(result.success).toBe(true);
  });

  it('rejects a malformed organizational reference', () => {
    expect(createUserSchema.safeParse(createPayload({ business_unit_id: 'nope' })).success).toBe(false);
  });

  it.each([
    ['2999-01-01', 'a future date'],
    ['2024-01-01', 'an implausibly young date'],
    ['1880-01-01', 'an implausibly old date'],
  ])('rejects %s as a date of birth (%s)', (dob) => {
    expect(createUserSchema.safeParse(createPayload({ date_of_birth: dob })).success).toBe(false);
  });

  it('accepts a realistic date of birth', () => {
    expect(createUserSchema.safeParse(createPayload({ date_of_birth: '1994-06-15' })).success).toBe(true);
  });
});

describe('editUserSchema', () => {
  it('has no password field', () => {
    /* Setting someone else's password is a separate, separately audited action. */
    const result = editUserSchema.safeParse(createPayload({ password: 'Str0ng@1' }));

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).not.toHaveProperty('password');
    }
  });
});

describe('profileSchema', () => {
  it('accepts the three fields a user owns', () => {
    const result = profileSchema.safeParse({
      personal_email: 'jane@personal.example',
      phone_number: '+91 98765 43210',
      avatar_url: 'https://cdn.example/a.png',
    });
    expect(result.success).toBe(true);
  });

  it('drops any administrative field it is handed', () => {
    /* The server rejects them outright; the client simply never sends them. */
    const result = profileSchema.safeParse({ first_name: 'Hacked', username: 'hacked' });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).not.toHaveProperty('first_name');
      expect(result.data).not.toHaveProperty('username');
    }
  });

  it('sends a cleared field as an explicit null', () => {
    const result = profileSchema.parse({ personal_email: '', phone_number: '', avatar_url: '' });
    expect(JSON.parse(JSON.stringify(result))).toEqual({
      personal_email: null,
      phone_number: null,
      avatar_url: null,
    });
  });
});

describe('resetPasswordSchema', () => {
  it('requires the confirmation to match', () => {
    const result = resetPasswordSchema.safeParse({
      new_password: 'Str0ng@1',
      confirm_password: 'Different@1',
      force_password_change: true,
      revoke_sessions: true,
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['confirm_password']);
    }
  });

  it('accepts a matching confirmation', () => {
    const result = resetPasswordSchema.safeParse({
      new_password: 'Str0ng@1',
      confirm_password: 'Str0ng@1',
      force_password_change: true,
      revoke_sessions: true,
    });
    expect(result.success).toBe(true);
  });
});

describe('changeOwnPasswordSchema', () => {
  it('rejects reusing the current password', () => {
    const result = changeOwnPasswordSchema.safeParse({
      current_password: 'Str0ng@1',
      new_password: 'Str0ng@1',
      confirm_password: 'Str0ng@1',
    });
    expect(result.success).toBe(false);
  });

  it('accepts a genuinely new password', () => {
    const result = changeOwnPasswordSchema.safeParse({
      current_password: 'Old@Pass1',
      new_password: 'Str0ng@1',
      confirm_password: 'Str0ng@1',
    });
    expect(result.success).toBe(true);
  });
});

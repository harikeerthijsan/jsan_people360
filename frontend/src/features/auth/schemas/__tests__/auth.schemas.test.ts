import {
  changePasswordSchema,
  forgotPasswordSchema,
  loginSchema,
  profileSchema,
  resetPasswordSchema,
} from '@/features/auth/schemas/auth.schemas';

describe('loginSchema', () => {
  it('normalises the email address', () => {
    const result = loginSchema.parse({
      email: '  Admin@Example.COM ',
      password: 'anything',
      remember_me: false,
    });
    expect(result.email).toBe('admin@example.com');
  });

  it('carries the remember_me flag through', () => {
    const result = loginSchema.parse({ email: 'a@b.com', password: 'anything', remember_me: true });
    expect(result.remember_me).toBe(true);
  });

  it('rejects a malformed email address', () => {
    const result = loginSchema.safeParse({ email: 'not-an-email', password: 'anything', remember_me: false });
    expect(result.success).toBe(false);
  });

  it('rejects an empty password', () => {
    const result = loginSchema.safeParse({ email: 'a@b.com', password: '', remember_me: false });
    expect(result.success).toBe(false);
  });

  it('accepts a weak password, because existing accounts predate the policy', () => {
    const result = loginSchema.safeParse({ email: 'a@b.com', password: 'old', remember_me: false });
    expect(result.success).toBe(true);
  });
});

describe('forgotPasswordSchema', () => {
  it('requires a valid email address', () => {
    expect(forgotPasswordSchema.safeParse({ email: 'nope' }).success).toBe(false);
    expect(forgotPasswordSchema.safeParse({ email: 'a@b.com' }).success).toBe(true);
  });
});

describe('resetPasswordSchema', () => {
  const token = 'a'.repeat(32);

  it.each([
    ['Short@1a', 'shorter than the minimum'],
    ['alllowercase@1', 'no uppercase letter'],
    ['ALLUPPERCASE@1', 'no lowercase letter'],
    ['NoDigitsHere@', 'no digit'],
    ['NoSpecialChar1', 'no special character'],
  ])('rejects %s (%s)', (password) => {
    const result = resetPasswordSchema.safeParse({
      token,
      new_password: password,
      confirm_password: password,
    });
    expect(result.success).toBe(false);
  });

  it('accepts a compliant password', () => {
    const result = resetPasswordSchema.safeParse({
      token,
      new_password: 'Str0ng@Password',
      confirm_password: 'Str0ng@Password',
    });
    expect(result.success).toBe(true);
  });

  it('reports mismatched confirmation on the confirm field', () => {
    const result = resetPasswordSchema.safeParse({
      token,
      new_password: 'Str0ng@Password',
      confirm_password: 'Different@Pass1',
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['confirm_password']);
      expect(result.error.issues[0]?.message).toBe('Passwords do not match');
    }
  });

  it('requires a token', () => {
    const result = resetPasswordSchema.safeParse({
      token: '',
      new_password: 'Str0ng@Password',
      confirm_password: 'Str0ng@Password',
    });
    expect(result.success).toBe(false);
  });
});

describe('changePasswordSchema', () => {
  it('rejects reusing the current password', () => {
    const result = changePasswordSchema.safeParse({
      current_password: 'Str0ng@Password',
      new_password: 'Str0ng@Password',
      confirm_password: 'Str0ng@Password',
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.path.includes('new_password'))).toBe(true);
    }
  });

  it('accepts a genuinely new password', () => {
    const result = changePasswordSchema.safeParse({
      current_password: 'Old@Password123',
      new_password: 'Str0ng@Password',
      confirm_password: 'Str0ng@Password',
    });
    expect(result.success).toBe(true);
  });
});

describe('profileSchema', () => {
  it('collapses internal whitespace in the name', () => {
    const result = profileSchema.parse({ full_name: '  Jane   Doe  ' });
    expect(result.full_name).toBe('Jane Doe');
  });

  it('rejects a name that is too short', () => {
    expect(profileSchema.safeParse({ full_name: 'J' }).success).toBe(false);
  });
});

import { profileSchema } from './schema';
const valid = {
  joining_date: '2026-09-01',
  joining_confirmed: true,
  first_name: 'Asha',
  last_name: 'Rao',
  date_of_birth: '1995-05-05',
  gender: 'female',
  blood_group: 'O+',
  marital_status: 'single',
  nationality: 'Indian',
  personal_email: 'asha@example.com',
  mobile_number: '9876543210',
  emergency_contact: { name: 'Anil Rao', relationship: 'Father', phone_number: '9876543211', email: null },
  addresses: [
    {
      address_type: 'current',
      address_line1: '1 Main Road',
      address_line2: null,
      city: 'Hyderabad',
      state: 'Telangana',
      country: 'India',
      postal_code: '500001',
    },
    {
      address_type: 'permanent',
      address_line1: '2 Park Road',
      address_line2: null,
      city: 'Hyderabad',
      state: 'Telangana',
      country: 'India',
      postal_code: '500002',
    },
  ],
  bank_details: {
    bank_name: 'HDFC Bank',
    account_holder_name: 'Asha Rao',
    account_number: '123456789012',
    ifsc_code: 'HDFC0001234',
    branch_name: 'Main',
  },
  aadhaar_number: '234567890123',
  pan_number: 'ABCDE1234F',
};
describe('preboarding profile validation', () => {
  it('accepts a complete profile', () => expect(profileSchema.safeParse(valid).success).toBe(true));
  it('requires joining confirmation', () =>
    expect(profileSchema.safeParse({ ...valid, joining_confirmed: false }).success).toBe(false));
  it('rejects invalid Aadhaar, PAN and IFSC', () => {
    expect(profileSchema.safeParse({ ...valid, aadhaar_number: '123' }).success).toBe(false);
    expect(profileSchema.safeParse({ ...valid, pan_number: 'bad' }).success).toBe(false);
    expect(
      profileSchema.safeParse({ ...valid, bank_details: { ...valid.bank_details, ifsc_code: 'bad' } })
        .success,
    ).toBe(false);
  });
});

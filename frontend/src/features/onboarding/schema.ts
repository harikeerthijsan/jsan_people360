import { z } from 'zod';

const address = z.object({
  address_type: z.enum(['current', 'permanent']),
  address_line1: z.string().min(3),
  address_line2: z.string().nullable().optional(),
  city: z.string().min(1),
  state: z.string().min(1),
  country: z.string().min(1),
  postal_code: z.string().min(2),
});
export const profileSchema = z.object({
  joining_date: z.string().min(1),
  joining_confirmed: z.boolean().refine(Boolean, 'Confirm the joining date'),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  date_of_birth: z.string().min(1),
  gender: z.enum(['male', 'female', 'non_binary', 'prefer_not_to_say']),
  blood_group: z.enum(['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']),
  marital_status: z.enum(['single', 'married', 'divorced', 'widowed', 'separated']),
  nationality: z.string().min(2),
  personal_email: z.string().email(),
  mobile_number: z.string().min(7),
  emergency_contact: z.object({
    name: z.string().min(2),
    relationship: z.string().min(2),
    phone_number: z.string().min(7),
    email: z.string().email().nullable().optional(),
  }),
  addresses: z
    .array(address)
    .length(2)
    .refine(
      (x) => new Set(x.map((a) => a.address_type)).size === 2,
      'Current and permanent addresses are required',
    ),
  bank_details: z.object({
    bank_name: z.string().min(2),
    account_holder_name: z.string().min(2),
    account_number: z.string().regex(/^[A-Za-z0-9]{6,34}$/, 'Invalid account number'),
    ifsc_code: z.string().regex(/^[A-Z]{4}0[A-Z0-9]{6}$/, 'Invalid IFSC'),
    branch_name: z.string().min(2),
  }),
  aadhaar_number: z.string().regex(/^[2-9][0-9]{11}$/, 'Invalid Aadhaar'),
  pan_number: z.string().regex(/^[A-Z]{5}[0-9]{4}[A-Z]$/, 'Invalid PAN'),
});
export type ProfileFormValues = z.infer<typeof profileSchema>;

import { z } from 'zod';
const uuid = z.string().uuid();
export const clientSchema = z.object({
  client_name: z.string().min(2),
  company_name: z.string().min(2),
  industry: z.string().min(2),
  contact_person: z.string().min(2),
  email: z.string().email(),
  phone: z.string().min(7),
  country: z.string().min(2),
  address: z.string().min(5),
  website: z.string().url().nullable(),
  status: z.enum(['active', 'inactive']),
});
export const projectSchema = z
  .object({
    project_name: z.string().min(2),
    client_id: uuid,
    description: z.string().min(5),
    start_date: z.string().min(1),
    end_date: z.string().nullable(),
    status: z.enum(['planned', 'active', 'on_hold', 'completed', 'cancelled']),
    project_manager_id: uuid,
    delivery_manager_id: uuid.nullable(),
    work_location_id: uuid.nullable(),
    is_billable: z.boolean(),
    technology_stack: z.string().transform((x) =>
      x
        .split(',')
        .map((y) => y.trim())
        .filter(Boolean),
    ),
    priority: z.enum(['low', 'medium', 'high', 'critical']),
  })
  .refine((x) => !x.end_date || x.end_date >= x.start_date, {
    message: 'End date must be on or after start date',
    path: ['end_date'],
  });
export const allocationSchema = z
  .object({
    employee_id: uuid,
    role: z.string().min(2),
    allocation_percentage: z.coerce.number().positive().max(100),
    start_date: z.string().min(1),
    end_date: z.string().nullable(),
    reporting_manager_id: uuid.nullable(),
    billable: z.boolean(),
    reason: z.string().min(3),
  })
  .refine((x) => !x.end_date || x.end_date >= x.start_date, {
    message: 'End date must be on or after start date',
    path: ['end_date'],
  });

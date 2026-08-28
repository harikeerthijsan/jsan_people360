import { candidateSchema } from './schema';
const valid = {
  job_opening_id: '123e4567-e89b-42d3-a456-426614174000',
  source_id: '123e4567-e89b-42d3-a456-426614174001',
  first_name: 'Asha',
  last_name: 'Rao',
  email: 'asha@example.com',
  mobile_number: '+919876543210',
  experience_years: 5,
  current_ctc: 900000,
  expected_ctc: 1200000,
  notice_period_days: 30,
  skills: ['React'],
  resume_document_id: '123e4567-e89b-42d3-a456-426614174002',
};
describe('candidateSchema', () => {
  it('accepts a valid candidate', () => expect(candidateSchema.safeParse(valid).success).toBe(true));
  it('requires a resume', () =>
    expect(candidateSchema.safeParse({ ...valid, resume_document_id: '' }).success).toBe(false));
  it('validates compensation', () =>
    expect(candidateSchema.safeParse({ ...valid, expected_ctc: 1 }).success).toBe(false));
  it('validates notice period', () =>
    expect(candidateSchema.safeParse({ ...valid, notice_period_days: 400 }).success).toBe(false));
});

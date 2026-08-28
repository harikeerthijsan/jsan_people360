import { requisitionSchema } from '../schema';
const id = '11111111-1111-4111-8111-111111111111';
const valid = {
  job_title: 'Senior Engineer',
  hiring_type: 'new_position',
  request_type: 'new_position',
  business_unit_id: id,
  team_id: null,
  location_id: id,
  designation_id: id,
  grade_id: null,
  employment_type_id: id,
  openings: 2,
  experience_min: 3,
  experience_max: 5,
  education: null,
  skills: ['Python'],
  certifications: [],
  salary_from: 100,
  salary_to: 200,
  budget_approved: true,
  hiring_manager_id: id,
  second_approver_id: id,
  hr_approver_id: id,
  recruiter_id: null,
  target_joining_date: '2099-01-01',
  priority: 'high',
  responsibilities: 'Build reliable systems',
  requirements: 'Strong engineering skills',
  benefits: null,
  working_model: 'hybrid',
  business_justification: 'Required for approved growth',
};
describe('requisition validation', () => {
  it('accepts a valid manpower request', () => expect(requisitionSchema.safeParse(valid).success).toBe(true));
  it('rejects invalid ranges and past targets', () =>
    expect(
      requisitionSchema.safeParse({
        ...valid,
        salary_from: 300,
        salary_to: 200,
        target_joining_date: '2020-01-01',
      }).success,
    ).toBe(false));
  it('requires at least one opening', () =>
    expect(requisitionSchema.safeParse({ ...valid, openings: 0 }).success).toBe(false));
});

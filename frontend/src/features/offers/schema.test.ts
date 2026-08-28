import { offerSchema } from './schema';

const id = '123e4567-e89b-42d3-a456-426614174000';
const validOffer = {
  candidate_id: id,
  template_id: null,
  ctc: 120,
  joining_date: '2099-03-01',
  probation_months: 6,
  notice_period_days: 30,
  reporting_manager_id: null,
  work_mode: 'hybrid',
  shift: null,
  benefits: 'Benefits',
  leave_policy_summary: 'Leave policy',
  working_hours: 'Working hours',
  confidentiality: 'Confidentiality',
  nda_required: false,
  additional_conditions: null,
  expiry_date: '2099-02-01',
  salary_components: [
    { name: 'Basic Salary', component_type: 'fixed', annual_amount: 60, is_employer_contribution: false },
    { name: 'HRA', component_type: 'fixed', annual_amount: 30, is_employer_contribution: false },
    {
      name: 'Special Allowance',
      component_type: 'fixed',
      annual_amount: 30,
      is_employer_contribution: false,
    },
  ],
  hr_executive_id: id,
  hr_manager_id: id,
  business_unit_head_id: id,
};

describe('offerSchema', () => {
  it('accepts a balanced compensation structure', () => {
    expect(offerSchema.safeParse(validOffer).success).toBe(true);
  });

  it('rejects components that do not equal CTC', () => {
    expect(offerSchema.safeParse({ ...validOffer, ctc: 121 }).success).toBe(false);
  });
});

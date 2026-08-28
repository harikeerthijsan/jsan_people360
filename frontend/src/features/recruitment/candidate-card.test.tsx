import { render, screen } from '@testing-library/react';
import { CandidateCard } from './components';

const candidate = {
  id: '1',
  candidate_code: 'CAN-000001',
  job_opening_id: '2',
  source_id: '3',
  stage_id: '4',
  recruiter_id: null,
  first_name: 'Asha',
  last_name: 'Rao',
  email: 'asha@example.com',
  mobile_number: '+919876543210',
  linkedin_url: null,
  current_company: null,
  current_designation: null,
  experience_years: '5.0',
  current_ctc: null,
  expected_ctc: null,
  notice_period_days: 30,
  current_location: null,
  preferred_location: null,
  certifications: null,
  tags: null,
  applied_at: '2026-08-05T00:00:00Z',
  stage: { id: '4', name: 'Screening', sequence: 2, category: 'active' },
  source: { id: '3', name: 'LinkedIn' },
  skills: [{ id: '5', name: 'React', proficiency: null }],
  documents: [],
  stage_history: [],
  notes: [],
};

test('candidate card displays identity, stage and skills', () => {
  render(<CandidateCard candidate={candidate} />);
  expect(screen.getByText('Asha Rao')).toBeInTheDocument();
  expect(screen.getByText('Screening')).toBeInTheDocument();
  expect(screen.getByText('React')).toBeInTheDocument();
});

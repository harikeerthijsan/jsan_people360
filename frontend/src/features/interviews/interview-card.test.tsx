import { render, screen } from '@testing-library/react';
import { InterviewCard } from './components';
const item = {
  id: '1',
  interview_code: 'INT-000001',
  candidate_id: '2',
  job_opening_id: '3',
  interview_type: 'technical',
  interview_round: 'Technical Round 1',
  starts_at: '2026-08-10T10:00:00Z',
  ends_at: '2026-08-10T11:00:00Z',
  time_zone: 'Asia/Kolkata',
  mode: 'online',
  meeting_link: null,
  location: null,
  recruiter_notes: null,
  status: 'scheduled',
  overall_score: null,
  overall_recommendation: null,
  decision: null,
  panels: [],
  feedback: [],
  history: [],
  attachments: [],
  created_at: '2026-08-01T00:00:00Z',
};
test('renders interview identity and status', () => {
  render(<InterviewCard item={item} />);
  expect(screen.getByText('Technical Round 1')).toBeInTheDocument();
  expect(screen.getByText('Scheduled')).toBeInTheDocument();
  expect(screen.getByText('Online')).toBeInTheDocument();
});

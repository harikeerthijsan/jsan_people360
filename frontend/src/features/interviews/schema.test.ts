import { scheduleSchema } from './schema';
const start = new Date(Date.now() + 86400000);
const end = new Date(start.getTime() + 3600000);
const valid = {
  candidate_id: '123e4567-e89b-42d3-a456-426614174000',
  interview_type: 'technical',
  interview_round: 'Round 1',
  starts_at: start.toISOString(),
  ends_at: end.toISOString(),
  time_zone: 'Asia/Kolkata',
  mode: 'online',
  meeting_link: 'https://meet.example.com/1',
  location: null,
  recruiter_notes: null,
  panels: [
    {
      employee_id: '123e4567-e89b-42d3-a456-426614174001',
      designation_id: null,
      panel_role: 'lead_interviewer',
    },
  ],
};
describe('scheduleSchema', () => {
  it('accepts a valid schedule', () => expect(scheduleSchema.safeParse(valid).success).toBe(true));
  it('requires a lead interviewer', () =>
    expect(
      scheduleSchema.safeParse({ ...valid, panels: [{ ...valid.panels[0], panel_role: 'observer' }] })
        .success,
    ).toBe(false));
  it('rejects an invalid duration', () =>
    expect(scheduleSchema.safeParse({ ...valid, ends_at: start.toISOString() }).success).toBe(false));
  it('allows an optional online meeting link', () =>
    expect(scheduleSchema.safeParse({ ...valid, meeting_link: null }).success).toBe(true));
});

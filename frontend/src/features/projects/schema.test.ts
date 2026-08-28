import { allocationSchema, projectSchema } from './schema';
const id = '123e4567-e89b-42d3-a456-426614174000';
describe('project allocation validation', () => {
  it('accepts allocation up to 100%', () =>
    expect(
      allocationSchema.safeParse({
        employee_id: id,
        role: 'Engineer',
        allocation_percentage: 100,
        start_date: '2026-08-10',
        end_date: '2026-09-10',
        reporting_manager_id: null,
        billable: true,
        reason: 'Delivery',
      }).success,
    ).toBe(true));
  it('rejects allocation over 100%', () =>
    expect(
      allocationSchema.safeParse({
        employee_id: id,
        role: 'Engineer',
        allocation_percentage: 101,
        start_date: '2026-08-10',
        end_date: null,
        reporting_manager_id: null,
        billable: true,
        reason: 'Delivery',
      }).success,
    ).toBe(false));
  it('requires project manager and valid dates', () =>
    expect(
      projectSchema.safeParse({
        project_name: 'Platform',
        client_id: id,
        description: 'Delivery project',
        start_date: '2026-09-10',
        end_date: '2026-08-10',
        status: 'active',
        project_manager_id: '',
        delivery_manager_id: null,
        work_location_id: null,
        is_billable: true,
        technology_stack: 'Python',
        priority: 'high',
      }).success,
    ).toBe(false));
});

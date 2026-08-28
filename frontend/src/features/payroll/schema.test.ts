import {
  assignmentFormSchema,
  componentFormSchema,
  leaveRuleFormSchema,
  moneyString,
  payrollConfigFormSchema,
  periodFormSchema,
  revisionFormSchema,
  structureFormSchema,
} from './schema';

const COMPONENT = {
  name: 'House Rent Allowance',
  code: 'HRA',
  component_type: 'earning' as const,
  calculation_type: 'percentage' as const,
  value: '40',
  percentage_basis: 'basic' as const,
  description: null,
  proration_allowed: true,
  attendance_impact: false,
  leave_impact: false,
  overtime_eligible: false,
  is_taxable: true,
};

const COMPENSATION = {
  salary_structure_id: '4dd0898a-0982-4c8f-9a1c-6f4dbb0b3a55',
  currency: 'INR',
  annual_ctc: '500000.00',
  annual_gross: '460000.00',
  monthly_gross: '38333.33',
  basic_salary: '20000.00',
  effective_from: '2026-01-01',
  components: [{ component_id: '4dd0898a-0982-4c8f-9a1c-6f4dbb0b3a55', value: '240000.00' }],
};

describe('moneyString', () => {
  it('accepts exact decimal strings', () => {
    expect(moneyString.safeParse('0').success).toBe(true);
    expect(moneyString.safeParse('500000.00').success).toBe(true);
  });

  it('rejects negatives, letters and float noise', () => {
    expect(moneyString.safeParse('-1').success).toBe(false);
    expect(moneyString.safeParse('abc').success).toBe(false);
    expect(moneyString.safeParse('1.999').success).toBe(false);
  });
});

describe('componentFormSchema', () => {
  it('accepts a coherent percentage component', () => {
    expect(componentFormSchema.safeParse(COMPONENT).success).toBe(true);
  });

  it('requires a basis for percentages', () => {
    const parsed = componentFormSchema.safeParse({ ...COMPONENT, percentage_basis: null });
    expect(parsed.success).toBe(false);
  });

  it('caps percentages at 100', () => {
    expect(componentFormSchema.safeParse({ ...COMPONENT, value: '140' }).success).toBe(false);
  });
});

describe('structureFormSchema', () => {
  const structure = {
    name: 'Standard Monthly',
    description: null,
    pay_frequency: 'monthly' as const,
    currency: 'INR',
    effective_from: null,
    effective_to: null,
    component_ids: ['4dd0898a-0982-4c8f-9a1c-6f4dbb0b3a55'],
  };

  it('needs at least one component', () => {
    expect(structureFormSchema.safeParse({ ...structure, component_ids: [] }).success).toBe(false);
  });

  it('refuses a window that ends before it starts', () => {
    const parsed = structureFormSchema.safeParse({
      ...structure,
      effective_from: '2026-06-01',
      effective_to: '2026-01-01',
    });
    expect(parsed.success).toBe(false);
  });
});

describe('compensation schemas', () => {
  it('assignment allows an empty reason', () => {
    expect(assignmentFormSchema.safeParse({ ...COMPENSATION, reason: null }).success).toBe(true);
  });

  it('revision demands a reason', () => {
    expect(revisionFormSchema.safeParse({ ...COMPENSATION, reason: '' }).success).toBe(false);
    expect(revisionFormSchema.safeParse({ ...COMPENSATION, reason: 'Annual increment' }).success).toBe(
      true,
    );
  });

  it('CTC must be positive', () => {
    expect(
      assignmentFormSchema.safeParse({ ...COMPENSATION, annual_ctc: '0', reason: null }).success,
    ).toBe(false);
  });
});

describe('payrollConfigFormSchema', () => {
  const CONFIG = {
    pay_frequency: 'monthly' as const,
    period_start_day: 1,
    period_end_day: 31,
    pay_day: 31,
    cutoff_day: 25,
    currency: 'INR',
    working_days_rule: 'working_days' as const,
    weekly_off_days: [5, 6],
    proration_basis: 'calendar_days' as const,
    unpaid_leave_treatment: 'deduct' as const,
    unpaid_leave_basis: 'calendar_days' as const,
    overtime_enabled: true,
    overtime_basis: 'basic' as const,
    overtime_multiplier: '1.5',
    overtime_min_hours: '1',
    overtime_max_hours: null,
    overtime_approval_required: true,
    standard_daily_hours: '8',
    deduct_absence: true,
    deduct_late_arrival: false,
    deduct_early_exit: false,
    require_approved_attendance: true,
    rounding_rule: 'none' as const,
    rounding_precision: null,
    reason: 'Initial configuration',
    effective_from: '2026-09-01',
  };

  it('accepts the defaults', () => {
    expect(payrollConfigFormSchema.safeParse(CONFIG).success).toBe(true);
  });

  it('demands a precision for custom rounding', () => {
    expect(
      payrollConfigFormSchema.safeParse({ ...CONFIG, rounding_rule: 'custom' }).success,
    ).toBe(false);
  });

  it('refuses a duplicate weekly off day', () => {
    expect(
      payrollConfigFormSchema.safeParse({ ...CONFIG, weekly_off_days: [6, 6] }).success,
    ).toBe(false);
  });

  it('refuses an inverted overtime window', () => {
    expect(
      payrollConfigFormSchema.safeParse({
        ...CONFIG,
        overtime_min_hours: '4',
        overtime_max_hours: '2',
      }).success,
    ).toBe(false);
  });

  it('demands a reason', () => {
    expect(payrollConfigFormSchema.safeParse({ ...CONFIG, reason: '' }).success).toBe(false);
  });
});

describe('periodFormSchema', () => {
  const PERIOD = {
    name: 'August 2026',
    start_date: '2026-08-01',
    end_date: '2026-08-31',
    pay_date: '2026-08-31',
    notes: null,
  };

  it('accepts a coherent period', () => {
    expect(periodFormSchema.safeParse(PERIOD).success).toBe(true);
  });

  it('refuses a period that ends before it starts', () => {
    expect(
      periodFormSchema.safeParse({ ...PERIOD, end_date: '2026-07-31' }).success,
    ).toBe(false);
  });

  it('refuses a pay date before the period starts', () => {
    expect(periodFormSchema.safeParse({ ...PERIOD, pay_date: '2026-07-15' }).success).toBe(false);
  });
});

describe('leaveRuleFormSchema', () => {
  const RULE = {
    leave_type_id: '4dd0898a-0982-4c8f-9a1c-6f4dbb0b3a55',
    treatment: 'unpaid' as const,
    deduction_basis: 'working_days' as const,
    description: null,
  };

  it('accepts an unpaid rule with a basis', () => {
    expect(leaveRuleFormSchema.safeParse(RULE).success).toBe(true);
  });

  it('refuses an unpaid rule without a basis', () => {
    expect(leaveRuleFormSchema.safeParse({ ...RULE, deduction_basis: null }).success).toBe(false);
  });

  it('accepts a paid rule with no basis', () => {
    expect(
      leaveRuleFormSchema.safeParse({ ...RULE, treatment: 'paid', deduction_basis: null }).success,
    ).toBe(true);
  });
});

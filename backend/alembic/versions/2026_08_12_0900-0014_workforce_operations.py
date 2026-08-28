"""Workforce operations: shifts, attendance, leave and timesheets.

Revision ID: 0014_workforce_operations
Revises: 0013_performance_management
Create Date: 2026-08-12 09:00:00

Eleven tables across three connected sub-domains. Ordered so that every table
follows the one it references: shifts, leave types and holiday calendars first,
then the records that point at them.

NOTE: the actor foreign keys below carry no ``use_alter``. Inside
``op.create_table`` SQLAlchemy *silently omits* a constraint marked that way, so
the columns would exist with nothing enforcing them -- a trap this project has
hit twice. It is needed only in the models, where it breaks a real import cycle.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_workforce_operations"
down_revision = "0013_performance_management"
branch_labels = None
depends_on = None

TIMESHEET_CODE_SEQUENCE = "timesheets_code_seq"

#: Dropped in reverse dependency order.
_TABLES = (
    "timesheet_entries",
    "timesheets",
    "holidays",
    "leave_requests",
    "leave_balances",
    "attendance_regularizations",
    "attendance_records",
    "employee_shifts",
    "holiday_calendars",
    "leave_types",
    "shifts",
)

#: name, code, type, start, end, grace minutes, break minutes, weekly off (Monday=0).
_SHIFTS = (
    ("General Shift", "GEN", "general", "09:30", "18:30", 15, 60, "[5, 6]"),
    ("Morning Shift", "MOR", "morning", "06:00", "14:30", 10, 30, "[5, 6]"),
    ("Evening Shift", "EVE", "evening", "14:00", "22:30", 10, 30, "[5, 6]"),
    ("Night Shift", "NGT", "night", "22:00", "06:30", 10, 45, "[5, 6]"),
)

#: name, code, annual allocation, carry forward, max carry forward, paid, needs a document, note.
_LEAVE_TYPES = (
    ("Casual Leave", "CL", 12, False, 0, True, False,
     "Short, planned personal absences. Does not carry into the next year."),
    ("Sick Leave", "SL", 12, False, 0, True, True,
     "Illness. A medical certificate is required beyond two consecutive days."),
    ("Earned Leave", "EL", 15, True, 30, True, False,
     "Accrued annual leave. Unused days carry forward up to thirty."),
    ("Maternity Leave", "ML", 182, False, 0, True, True,
     "Twenty-six weeks under the Maternity Benefit Act."),
    ("Paternity Leave", "PL", 5, False, 0, True, True, "Taken within six months of the birth."),
    ("Bereavement Leave", "BL", 5, False, 0, True, False, "Death of an immediate family member."),
    ("Comp Off", "CO", 0, False, 0, True, False,
     "Granted against approved work on a weekly off or holiday; not allocated annually."),
    ("Loss of Pay", "LOP", 0, False, 0, False, False,
     "Unpaid absence, used once every other entitlement is exhausted."),
)


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {TIMESHEET_CODE_SEQUENCE} START 1"))

    op.create_table('shifts',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('shift_type', sa.String(length=20), server_default='general', nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('grace_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('break_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('weekly_off', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("shift_type IN ('general', 'morning', 'evening', 'night', 'flexible')", name=op.f('ck_shifts_ck_shifts_type')),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_shifts_ck_shifts_status')),
    sa.CheckConstraint('break_minutes >= 0', name=op.f('ck_shifts_ck_shifts_break')),
    sa.CheckConstraint('grace_minutes >= 0', name=op.f('ck_shifts_ck_shifts_grace')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_shifts_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_shifts_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_shifts_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shifts')),
    sa.UniqueConstraint('code', name='uq_shifts_code'),
    comment='Configurable working patterns.'
    )
    op.create_index(op.f('ix_shifts_code'), 'shifts', ['code'], unique=False)
    op.create_index(op.f('ix_shifts_deleted_at'), 'shifts', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_shifts_name'), 'shifts', ['name'], unique=False)
    op.create_index(op.f('ix_shifts_shift_type'), 'shifts', ['shift_type'], unique=False)
    op.create_index(op.f('ix_shifts_status'), 'shifts', ['status'], unique=False)
    op.create_table('leave_types',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('annual_allocation', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('carry_forward', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('max_carry_forward', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('allows_negative', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_paid', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('requires_document', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_leave_types_ck_leave_types_status')),
    sa.CheckConstraint('annual_allocation >= 0', name=op.f('ck_leave_types_ck_leave_types_allocation')),
    sa.CheckConstraint('max_carry_forward >= 0', name=op.f('ck_leave_types_ck_leave_types_carry')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_leave_types_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_leave_types_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_leave_types_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leave_types')),
    sa.UniqueConstraint('code', name='uq_leave_types_code'),
    comment='Configurable leave categories.'
    )
    op.create_index(op.f('ix_leave_types_code'), 'leave_types', ['code'], unique=False)
    op.create_index(op.f('ix_leave_types_deleted_at'), 'leave_types', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_leave_types_name'), 'leave_types', ['name'], unique=False)
    op.create_index(op.f('ix_leave_types_status'), 'leave_types', ['status'], unique=False)
    op.create_table('holiday_calendars',
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_holiday_calendars_ck_holiday_calendars_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_holiday_calendars_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_holiday_calendars_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_holiday_calendars_location_id_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_holiday_calendars_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_holiday_calendars')),
    sa.UniqueConstraint('name', 'year', name='uq_holiday_calendars_name_year'),
    comment='Holiday calendars, scoped to a location.'
    )
    op.create_index(op.f('ix_holiday_calendars_deleted_at'), 'holiday_calendars', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_holiday_calendars_location_id'), 'holiday_calendars', ['location_id'], unique=False)
    op.create_index(op.f('ix_holiday_calendars_name'), 'holiday_calendars', ['name'], unique=False)
    op.create_index(op.f('ix_holiday_calendars_status'), 'holiday_calendars', ['status'], unique=False)
    op.create_index(op.f('ix_holiday_calendars_year'), 'holiday_calendars', ['year'], unique=False)
    op.create_table('employee_shifts',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('shift_id', sa.UUID(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name=op.f('ck_employee_shifts_ck_employee_shifts_dates')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_employee_shifts_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_employee_shifts_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_employee_shifts_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], name=op.f('fk_employee_shifts_shift_id_shifts'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_employee_shifts_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_employee_shifts')),
    comment='Shift assignment history.'
    )
    op.create_index(op.f('ix_employee_shifts_deleted_at'), 'employee_shifts', ['deleted_at'], unique=False)
    op.create_index('ix_employee_shifts_employee_from', 'employee_shifts', ['employee_id', 'effective_from'], unique=False)
    op.create_index(op.f('ix_employee_shifts_employee_id'), 'employee_shifts', ['employee_id'], unique=False)
    op.create_index(op.f('ix_employee_shifts_shift_id'), 'employee_shifts', ['shift_id'], unique=False)
    op.create_table('attendance_records',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('attendance_date', sa.Date(), nullable=False),
    sa.Column('shift_id', sa.UUID(), nullable=True),
    sa.Column('check_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('check_out_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('work_mode', sa.String(length=20), server_default='office', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='present', nullable=False),
    sa.Column('worked_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('late_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('early_exit_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('overtime_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('present', 'absent', 'half_day', 'leave', 'holiday', 'weekend')", name=op.f('ck_attendance_records_ck_attendance_status')),
    sa.CheckConstraint("work_mode IN ('office', 'remote', 'hybrid')", name=op.f('ck_attendance_records_ck_attendance_work_mode')),
    sa.CheckConstraint('worked_minutes >= 0', name=op.f('ck_attendance_records_ck_attendance_worked')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_attendance_records_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_attendance_records_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_attendance_records_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], name=op.f('fk_attendance_records_shift_id_shifts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_attendance_records_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attendance_records')),
    sa.UniqueConstraint('employee_id', 'attendance_date', name='uq_attendance_employee_date'),
    comment='Daily attendance, one row per employee per day.'
    )
    op.create_index('ix_attendance_date_status', 'attendance_records', ['attendance_date', 'status'], unique=False)
    op.create_index(op.f('ix_attendance_records_attendance_date'), 'attendance_records', ['attendance_date'], unique=False)
    op.create_index(op.f('ix_attendance_records_deleted_at'), 'attendance_records', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_attendance_records_employee_id'), 'attendance_records', ['employee_id'], unique=False)
    op.create_index(op.f('ix_attendance_records_status'), 'attendance_records', ['status'], unique=False)
    op.create_table('attendance_regularizations',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('attendance_date', sa.Date(), nullable=False),
    sa.Column('requested_check_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requested_check_out_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('supporting_document_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('decided_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name=op.f('ck_attendance_regularizations_ck_regularization_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_attendance_regularizations_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['employees.id'], name=op.f('fk_attendance_regularizations_decided_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_attendance_regularizations_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_attendance_regularizations_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['supporting_document_id'], ['documents.id'], name=op.f('fk_attendance_regularizations_supporting_document_id_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_attendance_regularizations_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attendance_regularizations')),
    comment='Requests to correct an attendance record.'
    )
    op.create_index(op.f('ix_attendance_regularizations_attendance_date'), 'attendance_regularizations', ['attendance_date'], unique=False)
    op.create_index(op.f('ix_attendance_regularizations_deleted_at'), 'attendance_regularizations', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_attendance_regularizations_employee_id'), 'attendance_regularizations', ['employee_id'], unique=False)
    op.create_index(op.f('ix_attendance_regularizations_status'), 'attendance_regularizations', ['status'], unique=False)
    op.create_index('ix_regularizations_status_date', 'attendance_regularizations', ['status', 'attendance_date'], unique=False)
    op.create_table('leave_balances',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('leave_type_id', sa.UUID(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('opening_balance', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('allocated', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('used', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('pending', sa.Numeric(precision=5, scale=1), server_default='0', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('year >= 2000', name=op.f('ck_leave_balances_ck_leave_balances_year')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_leave_balances_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_leave_balances_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_leave_balances_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['leave_type_id'], ['leave_types.id'], name=op.f('fk_leave_balances_leave_type_id_leave_types'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_leave_balances_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leave_balances')),
    sa.UniqueConstraint('employee_id', 'leave_type_id', 'year', name='uq_leave_balances_employee_type_year'),
    comment='Leave entitlement and consumption, per year.'
    )
    op.create_index(op.f('ix_leave_balances_deleted_at'), 'leave_balances', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_leave_balances_employee_id'), 'leave_balances', ['employee_id'], unique=False)
    op.create_index(op.f('ix_leave_balances_leave_type_id'), 'leave_balances', ['leave_type_id'], unique=False)
    op.create_index(op.f('ix_leave_balances_year'), 'leave_balances', ['year'], unique=False)
    op.create_table('leave_requests',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('leave_type_id', sa.UUID(), nullable=False),
    sa.Column('from_date', sa.Date(), nullable=False),
    sa.Column('to_date', sa.Date(), nullable=False),
    sa.Column('day_part', sa.String(length=20), server_default='full_day', nullable=False),
    sa.Column('days', sa.Numeric(precision=5, scale=1), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('supporting_document_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('decided_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("day_part IN ('full_day', 'first_half', 'second_half')", name=op.f('ck_leave_requests_ck_leave_requests_day_part')),
    sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name=op.f('ck_leave_requests_ck_leave_requests_status')),
    sa.CheckConstraint('days > 0', name=op.f('ck_leave_requests_ck_leave_requests_days')),
    sa.CheckConstraint('to_date >= from_date', name=op.f('ck_leave_requests_ck_leave_requests_dates')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_leave_requests_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['employees.id'], name=op.f('fk_leave_requests_decided_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_leave_requests_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_leave_requests_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['leave_type_id'], ['leave_types.id'], name=op.f('fk_leave_requests_leave_type_id_leave_types'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['supporting_document_id'], ['documents.id'], name=op.f('fk_leave_requests_supporting_document_id_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_leave_requests_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leave_requests')),
    comment='Leave applications and their approval state.'
    )
    op.create_index(op.f('ix_leave_requests_deleted_at'), 'leave_requests', ['deleted_at'], unique=False)
    op.create_index('ix_leave_requests_employee_dates', 'leave_requests', ['employee_id', 'from_date', 'to_date'], unique=False)
    op.create_index(op.f('ix_leave_requests_employee_id'), 'leave_requests', ['employee_id'], unique=False)
    op.create_index(op.f('ix_leave_requests_from_date'), 'leave_requests', ['from_date'], unique=False)
    op.create_index(op.f('ix_leave_requests_leave_type_id'), 'leave_requests', ['leave_type_id'], unique=False)
    op.create_index(op.f('ix_leave_requests_status'), 'leave_requests', ['status'], unique=False)
    op.create_index(op.f('ix_leave_requests_to_date'), 'leave_requests', ['to_date'], unique=False)
    op.create_table('holidays',
    sa.Column('calendar_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('holiday_date', sa.Date(), nullable=False),
    sa.Column('holiday_type', sa.String(length=20), server_default='public', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("holiday_type IN ('public', 'restricted', 'optional')", name=op.f('ck_holidays_ck_holidays_type')),
    sa.ForeignKeyConstraint(['calendar_id'], ['holiday_calendars.id'], name=op.f('fk_holidays_calendar_id_holiday_calendars'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_holidays_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_holidays_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_holidays_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_holidays')),
    sa.UniqueConstraint('calendar_id', 'holiday_date', name='uq_holidays_calendar_date'),
    comment='Individual holidays within a calendar.'
    )
    op.create_index(op.f('ix_holidays_calendar_id'), 'holidays', ['calendar_id'], unique=False)
    op.create_index('ix_holidays_date', 'holidays', ['holiday_date'], unique=False)
    op.create_index(op.f('ix_holidays_deleted_at'), 'holidays', ['deleted_at'], unique=False)
    op.create_table('timesheets',
    sa.Column('timesheet_code', sa.String(length=20), server_default=sa.text("'TS-' || lpad(nextval('timesheets_code_seq')::text, 6, '0')"), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('week_start_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('total_hours', sa.Numeric(precision=6, scale=2), server_default='0', nullable=False),
    sa.Column('billable_hours', sa.Numeric(precision=6, scale=2), server_default='0', nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('draft', 'submitted', 'approved', 'rejected')", name=op.f('ck_timesheets_ck_timesheets_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_timesheets_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['employees.id'], name=op.f('fk_timesheets_decided_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_timesheets_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_timesheets_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_timesheets_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_timesheets')),
    sa.UniqueConstraint('employee_id', 'week_start_date', name='uq_timesheets_employee_week'),
    sa.UniqueConstraint('timesheet_code', name=op.f('uq_timesheets_timesheet_code')),
    comment='Weekly timesheets.'
    )
    op.create_index(op.f('ix_timesheets_deleted_at'), 'timesheets', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_timesheets_employee_id'), 'timesheets', ['employee_id'], unique=False)
    op.create_index(op.f('ix_timesheets_status'), 'timesheets', ['status'], unique=False)
    op.create_index('ix_timesheets_status_week', 'timesheets', ['status', 'week_start_date'], unique=False)
    op.create_index(op.f('ix_timesheets_week_start_date'), 'timesheets', ['week_start_date'], unique=False)
    op.create_table('timesheet_entries',
    sa.Column('timesheet_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('work_date', sa.Date(), nullable=False),
    sa.Column('task', sa.String(length=200), nullable=False),
    sa.Column('hours', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('billable', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('hours > 0 AND hours <= 24', name=op.f('ck_timesheet_entries_ck_timesheet_entries_hours')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_timesheet_entries_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_timesheet_entries_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_timesheet_entries_project_id_projects'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['timesheet_id'], ['timesheets.id'], name=op.f('fk_timesheet_entries_timesheet_id_timesheets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_timesheet_entries_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_timesheet_entries')),
    comment='Individual timesheet lines.'
    )
    op.create_index('ix_timesheet_entries_date', 'timesheet_entries', ['work_date'], unique=False)
    op.create_index(op.f('ix_timesheet_entries_deleted_at'), 'timesheet_entries', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_timesheet_entries_project_id'), 'timesheet_entries', ['project_id'], unique=False)
    op.create_index(op.f('ix_timesheet_entries_timesheet_id'), 'timesheet_entries', ['timesheet_id'], unique=False)

    _seed()


def _seed() -> None:
    """Give the module something to run against on day one.

    A shift and a leave type are not sample data -- attendance cannot be marked
    without a shift, and leave cannot be applied for without a type. Seeding the
    Indian statutory set here means the first employee added to the system can
    already check in and apply for casual leave.
    """
    for name, code, kind, start, end, grace, brk, weekly_off in _SHIFTS:
        op.execute(
            sa.text(
                "INSERT INTO shifts(name, code, shift_type, start_time, end_time,"
                " grace_minutes, break_minutes, weekly_off)"
                " VALUES (:name, :code, :kind, CAST(:start AS time), CAST(:end AS time),"
                " :grace, :brk, CAST(:off AS jsonb))"
            ).bindparams(
                name=name, code=code, kind=kind, start=start, end=end,
                grace=grace, brk=brk, off=weekly_off,
            )
        )

    for name, code, allocation, carry, max_carry, paid, needs_document, description in _LEAVE_TYPES:
        op.execute(
            sa.text(
                "INSERT INTO leave_types(name, code, description, annual_allocation,"
                " carry_forward, max_carry_forward, is_paid, requires_document)"
                " VALUES (:name, :code, :description, :allocation, :carry, :max_carry, :paid, :doc)"
            ).bindparams(
                name=name, code=code, description=description, allocation=allocation,
                carry=carry, max_carry=max_carry, paid=paid, doc=needs_document,
            )
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_table(table)

    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {TIMESHEET_CODE_SEQUENCE}"))

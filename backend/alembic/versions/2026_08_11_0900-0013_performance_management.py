"""Performance management and goals.

Revision ID: 0013_performance_management
Revises: 0012_remove_practice_department
Create Date: 2026-08-11 09:00:00

Ten tables covering appraisal cycles, goals and their append-only progress,
the three review stages, recognitions, continuous feedback and an immutable
performance narrative.

Two notes on the shape:

* ``goal_ratings`` is one table for both review stages. A self rating and a
  manager rating of the same goal are the same measurement, so they share a
  table and are told apart by ``stage``.
* The two code sequences are created **before** the tables that default from
  them; a column default referencing a missing sequence fails at insert time
  rather than at migration time, which is the harder failure to find.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_performance_management"
down_revision = "0012_remove_practice_department"
branch_labels = None
depends_on = None

CYCLE_CODE_SEQUENCE = "performance_cycles_code_seq"
GOAL_CODE_SEQUENCE = "goals_code_seq"

#: Dropped in reverse order: every table below depends on something above it.
_TABLES = (
    "performance_history",
    "continuous_feedback",
    "recognitions",
    "final_reviews",
    "manager_reviews",
    "self_reviews",
    "goal_ratings",
    "goal_progress",
    "goals",
    "performance_cycles",
)


def upgrade() -> None:
    # NOTE: no ``use_alter`` on the actor foreign keys below. Inside
    # ``op.create_table`` SQLAlchemy *silently omits* a constraint marked that
    # way, so the columns would exist with nothing enforcing them. It is only
    # needed in the models, where it breaks a genuine import cycle; here the
    # ordering is explicit and ``users`` already exists.
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {CYCLE_CODE_SEQUENCE} START 1"))
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {GOAL_CODE_SEQUENCE} START 1"))

    op.create_table('performance_cycles',
    sa.Column('cycle_code', sa.String(length=20), server_default=sa.text("'PC-' || lpad(nextval('performance_cycles_code_seq')::text, 6, '0')"), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('financial_year', sa.String(length=20), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('self_review_deadline', sa.Date(), nullable=False),
    sa.Column('manager_review_deadline', sa.Date(), nullable=False),
    sa.Column('hr_review_deadline', sa.Date(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('draft', 'active', 'closed', 'archived')", name=op.f('ck_performance_cycles_ck_performance_cycles_status')),
    sa.CheckConstraint('end_date > start_date', name=op.f('ck_performance_cycles_ck_performance_cycles_dates')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_performance_cycles_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_performance_cycles_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_performance_cycles_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_performance_cycles')),
    sa.UniqueConstraint('cycle_code', name=op.f('uq_performance_cycles_cycle_code')),
    sa.UniqueConstraint('name', 'financial_year', name='uq_performance_cycles_name_year'),
    comment='Appraisal periods. Multiple cycles may exist across years.'
    )
    op.create_index(op.f('ix_performance_cycles_deleted_at'), 'performance_cycles', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_performance_cycles_financial_year'), 'performance_cycles', ['financial_year'], unique=False)
    op.create_index(op.f('ix_performance_cycles_name'), 'performance_cycles', ['name'], unique=False)
    op.create_index(op.f('ix_performance_cycles_status'), 'performance_cycles', ['status'], unique=False)
    op.create_index('ix_performance_cycles_status_start', 'performance_cycles', ['status', 'start_date'], unique=False)
    op.create_table('goals',
    sa.Column('goal_code', sa.String(length=20), server_default=sa.text("'GOAL-' || lpad(nextval('goals_code_seq')::text, 6, '0')"), nullable=False),
    sa.Column('cycle_id', sa.UUID(), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('assigned_by_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('success_criteria', sa.Text(), nullable=False),
    sa.Column('weightage', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('priority', sa.String(length=20), server_default='medium', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='not_started', nullable=False),
    sa.Column('completion_percentage', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name=op.f('ck_goals_ck_goals_priority')),
    sa.CheckConstraint("status IN ('not_started', 'in_progress', 'completed', 'blocked', 'cancelled')", name=op.f('ck_goals_ck_goals_status')),
    sa.CheckConstraint('completion_percentage >= 0 AND completion_percentage <= 100', name=op.f('ck_goals_ck_goals_completion')),
    sa.CheckConstraint('due_date >= start_date', name=op.f('ck_goals_ck_goals_dates')),
    sa.CheckConstraint('weightage > 0 AND weightage <= 100', name=op.f('ck_goals_ck_goals_weightage')),
    sa.ForeignKeyConstraint(['assigned_by_id'], ['employees.id'], name=op.f('fk_goals_assigned_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_goals_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], name=op.f('fk_goals_cycle_id_performance_cycles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_goals_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_goals_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_goals_project_id_projects'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_goals_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_goals')),
    sa.UniqueConstraint('goal_code', name=op.f('uq_goals_goal_code')),
    comment='Objectives assigned to an employee for one performance cycle.'
    )
    op.create_index(op.f('ix_goals_assigned_by_id'), 'goals', ['assigned_by_id'], unique=False)
    op.create_index(op.f('ix_goals_category'), 'goals', ['category'], unique=False)
    op.create_index('ix_goals_cycle_employee', 'goals', ['cycle_id', 'employee_id'], unique=False)
    op.create_index(op.f('ix_goals_cycle_id'), 'goals', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_goals_deleted_at'), 'goals', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_goals_due_date'), 'goals', ['due_date'], unique=False)
    op.create_index(op.f('ix_goals_employee_id'), 'goals', ['employee_id'], unique=False)
    op.create_index(op.f('ix_goals_priority'), 'goals', ['priority'], unique=False)
    op.create_index(op.f('ix_goals_project_id'), 'goals', ['project_id'], unique=False)
    op.create_index(op.f('ix_goals_status'), 'goals', ['status'], unique=False)
    op.create_index(op.f('ix_goals_title'), 'goals', ['title'], unique=False)
    op.create_table('goal_progress',
    sa.Column('goal_id', sa.UUID(), nullable=False),
    sa.Column('completion_percentage', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('evidence_document_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('completion_percentage >= 0 AND completion_percentage <= 100', name=op.f('ck_goal_progress_ck_goal_progress_completion')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_goal_progress_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_goal_progress_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['evidence_document_id'], ['documents.id'], name=op.f('fk_goal_progress_evidence_document_id_documents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], name=op.f('fk_goal_progress_goal_id_goals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_goal_progress_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_goal_progress')),
    comment='Append-only progress reports against a goal.'
    )
    op.create_index(op.f('ix_goal_progress_deleted_at'), 'goal_progress', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_goal_progress_evidence_document_id'), 'goal_progress', ['evidence_document_id'], unique=False)
    op.create_index('ix_goal_progress_goal_created', 'goal_progress', ['goal_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_goal_progress_goal_id'), 'goal_progress', ['goal_id'], unique=False)
    op.create_table('goal_ratings',
    sa.Column('goal_id', sa.UUID(), nullable=False),
    sa.Column('stage', sa.String(length=20), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('rated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("stage IN ('self', 'manager')", name=op.f('ck_goal_ratings_ck_goal_ratings_stage')),
    sa.CheckConstraint('rating IS NULL OR (rating >= 1 AND rating <= 5)', name=op.f('ck_goal_ratings_ck_goal_ratings_rating')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_goal_ratings_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_goal_ratings_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], name=op.f('fk_goal_ratings_goal_id_goals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rated_by_id'], ['employees.id'], name=op.f('fk_goal_ratings_rated_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_goal_ratings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_goal_ratings')),
    sa.UniqueConstraint('goal_id', 'stage', name='uq_goal_ratings_goal_stage'),
    comment='Per-goal scores from the self and manager review stages.'
    )
    op.create_index(op.f('ix_goal_ratings_deleted_at'), 'goal_ratings', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_goal_ratings_goal_id'), 'goal_ratings', ['goal_id'], unique=False)
    op.create_index(op.f('ix_goal_ratings_stage'), 'goal_ratings', ['stage'], unique=False)
    op.create_table('self_reviews',
    sa.Column('cycle_id', sa.UUID(), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('overall_rating', sa.Integer(), nullable=True),
    sa.Column('overall_comments', sa.Text(), nullable=True),
    sa.Column('achievements', sa.Text(), nullable=True),
    sa.Column('challenges', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('draft', 'submitted')", name=op.f('ck_self_reviews_ck_self_reviews_status')),
    sa.CheckConstraint('overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 5)', name=op.f('ck_self_reviews_ck_self_reviews_overall_rating')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_self_reviews_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], name=op.f('fk_self_reviews_cycle_id_performance_cycles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_self_reviews_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_self_reviews_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_self_reviews_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_self_reviews')),
    sa.UniqueConstraint('cycle_id', 'employee_id', name='uq_self_reviews_cycle_employee'),
    comment='One self-assessment per employee per cycle.'
    )
    op.create_index(op.f('ix_self_reviews_cycle_id'), 'self_reviews', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_self_reviews_deleted_at'), 'self_reviews', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_self_reviews_employee_id'), 'self_reviews', ['employee_id'], unique=False)
    op.create_index(op.f('ix_self_reviews_status'), 'self_reviews', ['status'], unique=False)
    op.create_table('manager_reviews',
    sa.Column('cycle_id', sa.UUID(), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=False),
    sa.Column('overall_rating', sa.Integer(), nullable=True),
    sa.Column('overall_feedback', sa.Text(), nullable=True),
    sa.Column('strengths', sa.Text(), nullable=True),
    sa.Column('improvement_areas', sa.Text(), nullable=True),
    sa.Column('recommendation', sa.String(length=30), server_default='none', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("recommendation IN ('promotion', 'salary_revision', 'training', 'pip', 'none')", name=op.f('ck_manager_reviews_ck_manager_reviews_recommendation')),
    sa.CheckConstraint("status IN ('draft', 'submitted')", name=op.f('ck_manager_reviews_ck_manager_reviews_status')),
    sa.CheckConstraint('overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 5)', name=op.f('ck_manager_reviews_ck_manager_reviews_overall_rating')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_manager_reviews_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], name=op.f('fk_manager_reviews_cycle_id_performance_cycles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_manager_reviews_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_manager_reviews_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['employees.id'], name=op.f('fk_manager_reviews_reviewer_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_manager_reviews_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manager_reviews')),
    sa.UniqueConstraint('cycle_id', 'employee_id', name='uq_manager_reviews_cycle_employee'),
    comment='One manager assessment per employee per cycle.'
    )
    op.create_index(op.f('ix_manager_reviews_cycle_id'), 'manager_reviews', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_manager_reviews_deleted_at'), 'manager_reviews', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_manager_reviews_employee_id'), 'manager_reviews', ['employee_id'], unique=False)
    op.create_index(op.f('ix_manager_reviews_reviewer_id'), 'manager_reviews', ['reviewer_id'], unique=False)
    op.create_index(op.f('ix_manager_reviews_status'), 'manager_reviews', ['status'], unique=False)
    op.create_table('final_reviews',
    sa.Column('cycle_id', sa.UUID(), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('finalised_by_id', sa.UUID(), nullable=True),
    sa.Column('final_rating', sa.Integer(), nullable=False),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('self_rating', sa.Integer(), nullable=True),
    sa.Column('manager_rating', sa.Integer(), nullable=True),
    sa.Column('goal_completion_percentage', sa.Integer(), nullable=True),
    sa.Column('finalised_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('final_rating IS NULL OR (final_rating >= 1 AND final_rating <= 5)', name=op.f('ck_final_reviews_ck_final_reviews_final_rating')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_final_reviews_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], name=op.f('fk_final_reviews_cycle_id_performance_cycles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_final_reviews_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_final_reviews_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['finalised_by_id'], ['employees.id'], name=op.f('fk_final_reviews_finalised_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_final_reviews_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_final_reviews')),
    sa.UniqueConstraint('cycle_id', 'employee_id', name='uq_final_reviews_cycle_employee'),
    comment='The rating of record for an employee in a cycle.'
    )
    op.create_index(op.f('ix_final_reviews_cycle_id'), 'final_reviews', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_final_reviews_deleted_at'), 'final_reviews', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_final_reviews_employee_id'), 'final_reviews', ['employee_id'], unique=False)
    op.create_index(op.f('ix_final_reviews_final_rating'), 'final_reviews', ['final_rating'], unique=False)
    op.create_table('recognitions',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('awarded_by_id', sa.UUID(), nullable=True),
    sa.Column('recognition_type', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('awarded_on', sa.Date(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("recognition_type IN ('star_performer', 'innovation', 'team_player', 'customer_appreciation', 'leadership')", name=op.f('ck_recognitions_ck_recognitions_type')),
    sa.ForeignKeyConstraint(['awarded_by_id'], ['employees.id'], name=op.f('fk_recognitions_awarded_by_id_employees'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_recognitions_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_recognitions_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_recognitions_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_recognitions_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recognitions')),
    comment='Recognitions awarded to employees.'
    )
    op.create_index(op.f('ix_recognitions_awarded_by_id'), 'recognitions', ['awarded_by_id'], unique=False)
    op.create_index(op.f('ix_recognitions_awarded_on'), 'recognitions', ['awarded_on'], unique=False)
    op.create_index(op.f('ix_recognitions_deleted_at'), 'recognitions', ['deleted_at'], unique=False)
    op.create_index('ix_recognitions_employee_awarded', 'recognitions', ['employee_id', 'awarded_on'], unique=False)
    op.create_index(op.f('ix_recognitions_employee_id'), 'recognitions', ['employee_id'], unique=False)
    op.create_index(op.f('ix_recognitions_recognition_type'), 'recognitions', ['recognition_type'], unique=False)
    op.create_table('continuous_feedback',
    sa.Column('from_employee_id', sa.UUID(), nullable=False),
    sa.Column('to_employee_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('visibility', sa.String(length=20), server_default='private', nullable=False),
    sa.Column('feedback_date', sa.Date(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("category IN ('appreciation', 'suggestion', 'improvement', 'achievement', 'recognition')", name=op.f('ck_continuous_feedback_ck_feedback_category')),
    sa.CheckConstraint("visibility IN ('private', 'manager', 'public')", name=op.f('ck_continuous_feedback_ck_feedback_visibility')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_continuous_feedback_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_continuous_feedback_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['from_employee_id'], ['employees.id'], name=op.f('fk_continuous_feedback_from_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_employee_id'], ['employees.id'], name=op.f('fk_continuous_feedback_to_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_continuous_feedback_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_continuous_feedback')),
    comment='Continuous feedback between employees.'
    )
    op.create_index(op.f('ix_continuous_feedback_category'), 'continuous_feedback', ['category'], unique=False)
    op.create_index(op.f('ix_continuous_feedback_deleted_at'), 'continuous_feedback', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_continuous_feedback_feedback_date'), 'continuous_feedback', ['feedback_date'], unique=False)
    op.create_index(op.f('ix_continuous_feedback_from_employee_id'), 'continuous_feedback', ['from_employee_id'], unique=False)
    op.create_index(op.f('ix_continuous_feedback_to_employee_id'), 'continuous_feedback', ['to_employee_id'], unique=False)
    op.create_index('ix_feedback_recipient_date', 'continuous_feedback', ['to_employee_id', 'feedback_date'], unique=False)
    op.create_table('performance_history',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('cycle_id', sa.UUID(), nullable=True),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_performance_history_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cycle_id'], ['performance_cycles.id'], name=op.f('fk_performance_history_cycle_id_performance_cycles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_performance_history_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_performance_history_employee_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_performance_history_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_performance_history')),
    comment='Append-only narrative of performance events.'
    )
    op.create_index(op.f('ix_performance_history_cycle_id'), 'performance_history', ['cycle_id'], unique=False)
    op.create_index(op.f('ix_performance_history_deleted_at'), 'performance_history', ['deleted_at'], unique=False)
    op.create_index('ix_performance_history_employee_created', 'performance_history', ['employee_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_performance_history_employee_id'), 'performance_history', ['employee_id'], unique=False)
    op.create_index(op.f('ix_performance_history_event_type'), 'performance_history', ['event_type'], unique=False)


def downgrade() -> None:
    for table in _TABLES:
        op.drop_table(table)

    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {GOAL_CODE_SEQUENCE}"))
    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {CYCLE_CODE_SEQUENCE}"))

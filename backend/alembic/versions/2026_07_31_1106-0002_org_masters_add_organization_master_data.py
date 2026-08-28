"""Add organization master data tables

Creates the nine master tables the Organization Management module owns. Every
future HR module references these rather than storing duplicate values.

Hierarchy:  business_units -> practices -> departments -> teams
                                        -> designations
Reference:  organizations, locations, employment_types, grades

Each table carries the platform audit contract (UUID primary key, created_at /
updated_at, created_by / updated_by, soft delete) supplied by AuditableBase.

Two conventions worth noting:

* Names and codes are enforced unique on ``lower(column)``. A plain UNIQUE
  constraint would accept both "GIS" and "gis", which is a data-quality bug in
  master data that other modules reference.
* Hierarchy foreign keys use ``ON DELETE RESTRICT``. Archiving is the supported
  way to retire a record; a hard delete that orphaned children would corrupt
  the tree.

Revision ID: 0002_org_masters
Revises: 0001_initial
Created: 2026-07-31 11:06:32.612709+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_org_masters"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the master tables, parents before children."""
    op.create_table('business_units',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_business_units_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_business_units_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_business_units_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_business_units_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_business_units')),
    comment='Top level of the organizational hierarchy.'
    )
    op.create_index(op.f('ix_business_units_code'), 'business_units', ['code'], unique=False)
    op.create_index(op.f('ix_business_units_deleted_at'), 'business_units', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_business_units_name'), 'business_units', ['name'], unique=False)
    op.create_index(op.f('ix_business_units_status'), 'business_units', ['status'], unique=False)
    op.create_index('uq_business_units_code_lower', 'business_units', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_business_units_name_lower', 'business_units', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('employment_types',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_employment_types_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_employment_types_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_employment_types_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_employment_types_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_employment_types')),
    comment='Contractual basis of an engagement.'
    )
    op.create_index(op.f('ix_employment_types_code'), 'employment_types', ['code'], unique=False)
    op.create_index(op.f('ix_employment_types_deleted_at'), 'employment_types', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_employment_types_name'), 'employment_types', ['name'], unique=False)
    op.create_index(op.f('ix_employment_types_status'), 'employment_types', ['status'], unique=False)
    op.create_index('uq_employment_types_code_lower', 'employment_types', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_employment_types_name_lower', 'employment_types', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('grades',
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_grades_status')),
    sa.CheckConstraint('level >= 1', name=op.f('ck_grades_level_positive')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_grades_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_grades_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_grades_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_grades')),
    comment='Compensation and seniority bands.'
    )
    op.create_index(op.f('ix_grades_code'), 'grades', ['code'], unique=False)
    op.create_index(op.f('ix_grades_deleted_at'), 'grades', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_grades_level'), 'grades', ['level'], unique=False)
    op.create_index(op.f('ix_grades_name'), 'grades', ['name'], unique=False)
    op.create_index(op.f('ix_grades_status'), 'grades', ['status'], unique=False)
    op.create_index('uq_grades_code_lower', 'grades', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_grades_name_lower', 'grades', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('locations',
    sa.Column('country', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=100), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_locations_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_locations_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_locations_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_locations_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_locations')),
    comment='Physical offices and work sites.'
    )
    op.create_index(op.f('ix_locations_city'), 'locations', ['city'], unique=False)
    op.create_index(op.f('ix_locations_code'), 'locations', ['code'], unique=False)
    op.create_index(op.f('ix_locations_country'), 'locations', ['country'], unique=False)
    op.create_index(op.f('ix_locations_deleted_at'), 'locations', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_locations_name'), 'locations', ['name'], unique=False)
    op.create_index(op.f('ix_locations_status'), 'locations', ['status'], unique=False)
    op.create_index('uq_locations_code_lower', 'locations', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_locations_name_lower', 'locations', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('organizations',
    sa.Column('legal_name', sa.String(length=250), nullable=False),
    sa.Column('registration_number', sa.String(length=100), nullable=False),
    sa.Column('gst_number', sa.String(length=15), nullable=True),
    sa.Column('pan_number', sa.String(length=10), nullable=True),
    sa.Column('logo_url', sa.String(length=1024), nullable=True),
    sa.Column('website', sa.String(length=255), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('address_line1', sa.String(length=255), nullable=False),
    sa.Column('address_line2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=100), nullable=False),
    sa.Column('country', sa.String(length=100), nullable=False),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_organizations_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_organizations_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_organizations_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_organizations_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations')),
    comment='Legal entities the platform is operated for.'
    )
    op.create_index(op.f('ix_organizations_deleted_at'), 'organizations', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_organizations_name'), 'organizations', ['name'], unique=False)
    op.create_index(op.f('ix_organizations_status'), 'organizations', ['status'], unique=False)
    op.create_index('uq_organizations_name_lower', 'organizations', [sa.literal_column('lower(name)')], unique=True)
    op.create_index('uq_organizations_registration_number_lower', 'organizations', [sa.literal_column('lower(registration_number)')], unique=True)
    op.create_table('practices',
    sa.Column('business_unit_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_practices_status')),
    sa.ForeignKeyConstraint(['business_unit_id'], ['business_units.id'], name=op.f('fk_practices_business_unit_id_business_units'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_practices_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_practices_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_practices_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_practices')),
    comment='Capability areas within a business unit.'
    )
    op.create_index(op.f('ix_practices_business_unit_id'), 'practices', ['business_unit_id'], unique=False)
    op.create_index(op.f('ix_practices_code'), 'practices', ['code'], unique=False)
    op.create_index(op.f('ix_practices_deleted_at'), 'practices', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_practices_name'), 'practices', ['name'], unique=False)
    op.create_index(op.f('ix_practices_status'), 'practices', ['status'], unique=False)
    op.create_index('uq_practices_business_unit_id_name_lower', 'practices', [sa.literal_column('business_unit_id'), sa.literal_column('lower(name)')], unique=True)
    op.create_index('uq_practices_code_lower', 'practices', [sa.literal_column('lower(code)')], unique=True)
    op.create_table('departments',
    sa.Column('practice_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_departments_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_departments_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_departments_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['practice_id'], ['practices.id'], name=op.f('fk_departments_practice_id_practices'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_departments_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_departments')),
    comment='Functional groups within a practice.'
    )
    op.create_index(op.f('ix_departments_code'), 'departments', ['code'], unique=False)
    op.create_index(op.f('ix_departments_deleted_at'), 'departments', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_departments_name'), 'departments', ['name'], unique=False)
    op.create_index(op.f('ix_departments_practice_id'), 'departments', ['practice_id'], unique=False)
    op.create_index(op.f('ix_departments_status'), 'departments', ['status'], unique=False)
    op.create_index('uq_departments_code_lower', 'departments', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_departments_practice_id_name_lower', 'departments', [sa.literal_column('practice_id'), sa.literal_column('lower(name)')], unique=True)
    op.create_table('designations',
    sa.Column('department_id', sa.UUID(), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_designations_status')),
    sa.CheckConstraint('level >= 1', name=op.f('ck_designations_level_positive')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_designations_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_designations_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_designations_department_id_departments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_designations_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_designations')),
    comment='Job titles within a department.'
    )
    op.create_index(op.f('ix_designations_code'), 'designations', ['code'], unique=False)
    op.create_index(op.f('ix_designations_deleted_at'), 'designations', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_designations_department_id'), 'designations', ['department_id'], unique=False)
    op.create_index(op.f('ix_designations_level'), 'designations', ['level'], unique=False)
    op.create_index(op.f('ix_designations_name'), 'designations', ['name'], unique=False)
    op.create_index(op.f('ix_designations_status'), 'designations', ['status'], unique=False)
    op.create_index('uq_designations_code_lower', 'designations', [sa.literal_column('lower(code)')], unique=True)
    op.create_index('uq_designations_department_id_name_lower', 'designations', [sa.literal_column('department_id'), sa.literal_column('lower(name)')], unique=True)
    op.create_table('teams',
    sa.Column('department_id', sa.UUID(), nullable=False),
    sa.Column('manager_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_teams_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_teams_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_teams_deleted_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_teams_department_id_departments'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['manager_id'], ['users.id'], name=op.f('fk_teams_manager_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_teams_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teams')),
    comment='Teams within a department.'
    )
    op.create_index(op.f('ix_teams_deleted_at'), 'teams', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_teams_department_id'), 'teams', ['department_id'], unique=False)
    op.create_index(op.f('ix_teams_manager_id'), 'teams', ['manager_id'], unique=False)
    op.create_index(op.f('ix_teams_name'), 'teams', ['name'], unique=False)
    op.create_index(op.f('ix_teams_status'), 'teams', ['status'], unique=False)
    op.create_index('uq_teams_department_id_name_lower', 'teams', [sa.literal_column('department_id'), sa.literal_column('lower(name)')], unique=True)


def downgrade() -> None:
    """Drop the master tables, children before parents."""
    op.drop_index('uq_teams_department_id_name_lower', table_name='teams')
    op.drop_index(op.f('ix_teams_status'), table_name='teams')
    op.drop_index(op.f('ix_teams_name'), table_name='teams')
    op.drop_index(op.f('ix_teams_manager_id'), table_name='teams')
    op.drop_index(op.f('ix_teams_department_id'), table_name='teams')
    op.drop_index(op.f('ix_teams_deleted_at'), table_name='teams')
    op.drop_table('teams')
    op.drop_index('uq_designations_department_id_name_lower', table_name='designations')
    op.drop_index('uq_designations_code_lower', table_name='designations')
    op.drop_index(op.f('ix_designations_status'), table_name='designations')
    op.drop_index(op.f('ix_designations_name'), table_name='designations')
    op.drop_index(op.f('ix_designations_level'), table_name='designations')
    op.drop_index(op.f('ix_designations_department_id'), table_name='designations')
    op.drop_index(op.f('ix_designations_deleted_at'), table_name='designations')
    op.drop_index(op.f('ix_designations_code'), table_name='designations')
    op.drop_table('designations')
    op.drop_index('uq_departments_practice_id_name_lower', table_name='departments')
    op.drop_index('uq_departments_code_lower', table_name='departments')
    op.drop_index(op.f('ix_departments_status'), table_name='departments')
    op.drop_index(op.f('ix_departments_practice_id'), table_name='departments')
    op.drop_index(op.f('ix_departments_name'), table_name='departments')
    op.drop_index(op.f('ix_departments_deleted_at'), table_name='departments')
    op.drop_index(op.f('ix_departments_code'), table_name='departments')
    op.drop_table('departments')
    op.drop_index('uq_practices_code_lower', table_name='practices')
    op.drop_index('uq_practices_business_unit_id_name_lower', table_name='practices')
    op.drop_index(op.f('ix_practices_status'), table_name='practices')
    op.drop_index(op.f('ix_practices_name'), table_name='practices')
    op.drop_index(op.f('ix_practices_deleted_at'), table_name='practices')
    op.drop_index(op.f('ix_practices_code'), table_name='practices')
    op.drop_index(op.f('ix_practices_business_unit_id'), table_name='practices')
    op.drop_table('practices')
    op.drop_index('uq_organizations_registration_number_lower', table_name='organizations')
    op.drop_index('uq_organizations_name_lower', table_name='organizations')
    op.drop_index(op.f('ix_organizations_status'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_name'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_deleted_at'), table_name='organizations')
    op.drop_table('organizations')
    op.drop_index('uq_locations_name_lower', table_name='locations')
    op.drop_index('uq_locations_code_lower', table_name='locations')
    op.drop_index(op.f('ix_locations_status'), table_name='locations')
    op.drop_index(op.f('ix_locations_name'), table_name='locations')
    op.drop_index(op.f('ix_locations_deleted_at'), table_name='locations')
    op.drop_index(op.f('ix_locations_country'), table_name='locations')
    op.drop_index(op.f('ix_locations_code'), table_name='locations')
    op.drop_index(op.f('ix_locations_city'), table_name='locations')
    op.drop_table('locations')
    op.drop_index('uq_grades_name_lower', table_name='grades')
    op.drop_index('uq_grades_code_lower', table_name='grades')
    op.drop_index(op.f('ix_grades_status'), table_name='grades')
    op.drop_index(op.f('ix_grades_name'), table_name='grades')
    op.drop_index(op.f('ix_grades_level'), table_name='grades')
    op.drop_index(op.f('ix_grades_deleted_at'), table_name='grades')
    op.drop_index(op.f('ix_grades_code'), table_name='grades')
    op.drop_table('grades')
    op.drop_index('uq_employment_types_name_lower', table_name='employment_types')
    op.drop_index('uq_employment_types_code_lower', table_name='employment_types')
    op.drop_index(op.f('ix_employment_types_status'), table_name='employment_types')
    op.drop_index(op.f('ix_employment_types_name'), table_name='employment_types')
    op.drop_index(op.f('ix_employment_types_deleted_at'), table_name='employment_types')
    op.drop_index(op.f('ix_employment_types_code'), table_name='employment_types')
    op.drop_table('employment_types')
    op.drop_index('uq_business_units_name_lower', table_name='business_units')
    op.drop_index('uq_business_units_code_lower', table_name='business_units')
    op.drop_index(op.f('ix_business_units_status'), table_name='business_units')
    op.drop_index(op.f('ix_business_units_name'), table_name='business_units')
    op.drop_index(op.f('ix_business_units_deleted_at'), table_name='business_units')
    op.drop_index(op.f('ix_business_units_code'), table_name='business_units')
    op.drop_table('business_units')


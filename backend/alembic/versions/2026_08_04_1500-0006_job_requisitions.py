"""Job requisition and workforce planning.

Revision ID: 0006_job_requisitions
Revises: 0005_document_vault
"""
from collections.abc import Sequence
from alembic import op

revision: str = "0006_job_requisitions"
down_revision: str | None = "0005_document_vault"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_COLUMNS = """
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), created_by uuid REFERENCES users(id) ON DELETE SET NULL,
 updated_by uuid REFERENCES users(id) ON DELETE SET NULL, deleted_at timestamptz,
 deleted_by uuid REFERENCES users(id) ON DELETE SET NULL
"""

def upgrade() -> None:
    op.execute("CREATE SEQUENCE job_requisitions_code_seq AS bigint START WITH 1")
    op.execute(f"""CREATE TABLE job_requisitions ({AUDIT_COLUMNS},
      requisition_code varchar(20) NOT NULL UNIQUE DEFAULT 'REQ-' || lpad(nextval('job_requisitions_code_seq')::text,6,'0'),
      job_title varchar(200) NOT NULL, hiring_type varchar(30) NOT NULL, request_type varchar(30) NOT NULL,
      status varchar(30) NOT NULL DEFAULT 'draft', priority varchar(20) NOT NULL DEFAULT 'medium',
      business_unit_id uuid NOT NULL REFERENCES business_units(id), practice_id uuid NOT NULL REFERENCES practices(id),
      department_id uuid NOT NULL REFERENCES departments(id), team_id uuid REFERENCES teams(id),
      location_id uuid NOT NULL REFERENCES locations(id), designation_id uuid NOT NULL REFERENCES designations(id),
      grade_id uuid REFERENCES grades(id), employment_type_id uuid NOT NULL REFERENCES employment_types(id),
      openings integer NOT NULL CHECK(openings > 0), experience_min integer NOT NULL DEFAULT 0 CHECK(experience_min >= 0),
      experience_max integer, education varchar(500), skills jsonb NOT NULL DEFAULT '[]', certifications jsonb NOT NULL DEFAULT '[]',
      salary_from numeric(14,2), salary_to numeric(14,2), budget_approved boolean NOT NULL DEFAULT false,
      hiring_manager_id uuid NOT NULL REFERENCES users(id), department_head_id uuid NOT NULL REFERENCES users(id),
      hr_approver_id uuid NOT NULL REFERENCES users(id), recruiter_id uuid REFERENCES users(id) ON DELETE SET NULL,
      target_joining_date date NOT NULL, responsibilities text NOT NULL, requirements text NOT NULL,
      benefits text, working_model varchar(20) NOT NULL, business_justification text NOT NULL,
      submitted_at timestamptz, approved_at timestamptz, closed_at timestamptz, current_approval_sequence integer,
      CHECK(salary_from IS NULL OR salary_to IS NULL OR salary_from <= salary_to),
      CHECK(experience_max IS NULL OR experience_min <= experience_max))""")
    op.execute("CREATE INDEX ix_requisitions_status_priority ON job_requisitions(status,priority)")
    op.execute("CREATE INDEX ix_requisitions_department_created ON job_requisitions(department_id,created_at)")
    op.execute(f"""CREATE TABLE requisition_approvals ({AUDIT_COLUMNS}, requisition_id uuid NOT NULL REFERENCES job_requisitions(id) ON DELETE CASCADE,
      sequence integer NOT NULL, role_name varchar(80) NOT NULL, approver_id uuid NOT NULL REFERENCES users(id), status varchar(30) NOT NULL DEFAULT 'waiting', comments text, acted_at timestamptz,
      UNIQUE(requisition_id,sequence))""")
    op.execute(f"""CREATE TABLE requisition_attachments ({AUDIT_COLUMNS}, requisition_id uuid NOT NULL REFERENCES job_requisitions(id) ON DELETE CASCADE,
      document_id uuid NOT NULL UNIQUE REFERENCES documents(id), attachment_type varchar(40) NOT NULL)""")
    op.execute(f"""CREATE TABLE requisition_history ({AUDIT_COLUMNS}, requisition_id uuid NOT NULL REFERENCES job_requisitions(id) ON DELETE CASCADE,
      action varchar(80) NOT NULL, from_status varchar(30), to_status varchar(30) NOT NULL, comments text, context jsonb)""")
    op.execute(f"""CREATE TABLE notifications ({AUDIT_COLUMNS}, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title varchar(200) NOT NULL, message text NOT NULL, link varchar(500), notification_type varchar(50) NOT NULL, read_at timestamptz)""")
    for table in ("requisition_approvals", "requisition_attachments", "requisition_history"):
        op.execute(f"CREATE INDEX ix_{table}_requisition_id ON {table}(requisition_id)")
    op.execute("CREATE INDEX ix_notifications_user_id ON notifications(user_id)")

def downgrade() -> None:
    for table in ("notifications", "requisition_history", "requisition_attachments", "requisition_approvals", "job_requisitions"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE job_requisitions_code_seq")

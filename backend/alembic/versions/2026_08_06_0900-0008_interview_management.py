"""Interview management and scheduling.

Revision ID: 0008_interview_management
Revises: 0007_recruitment_ats
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0008_interview_management"
down_revision: str | None = "0007_recruitment_ats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT = """id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), created_by uuid REFERENCES users(id) ON DELETE SET NULL, updated_by uuid REFERENCES users(id) ON DELETE SET NULL, deleted_at timestamptz, deleted_by uuid REFERENCES users(id) ON DELETE SET NULL"""


def upgrade() -> None:
    op.execute("CREATE SEQUENCE interviews_code_seq AS bigint START WITH 1")
    op.execute(f"""CREATE TABLE interviews ({AUDIT}, interview_code varchar(20) NOT NULL UNIQUE DEFAULT 'INT-' || lpad(nextval('interviews_code_seq')::text,6,'0'), candidate_id uuid NOT NULL REFERENCES candidates(id), job_opening_id uuid NOT NULL REFERENCES job_openings(id), interview_type varchar(30) NOT NULL, interview_round varchar(100) NOT NULL, starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, time_zone varchar(100) NOT NULL, mode varchar(20) NOT NULL, meeting_link varchar(1000), location varchar(500), recruiter_notes text, status varchar(30) NOT NULL DEFAULT 'scheduled', overall_score numeric(4,2), overall_recommendation varchar(30), decision varchar(30), CHECK(ends_at > starts_at), CHECK(mode IN ('online','offline','hybrid')))""")
    op.execute(f"""CREATE TABLE interview_panels ({AUDIT}, interview_id uuid NOT NULL REFERENCES interviews(id) ON DELETE CASCADE, employee_id uuid NOT NULL REFERENCES employees(id), designation_id uuid REFERENCES designations(id) ON DELETE SET NULL, panel_role varchar(30) NOT NULL, status varchar(30) NOT NULL DEFAULT 'assigned', UNIQUE(interview_id,employee_id))""")
    op.execute(f"""CREATE TABLE interview_feedback ({AUDIT}, interview_id uuid NOT NULL REFERENCES interviews(id) ON DELETE CASCADE, interviewer_id uuid NOT NULL REFERENCES employees(id), overall_comments text NOT NULL, recommendation varchar(30) NOT NULL, submitted_at timestamptz NOT NULL DEFAULT now(), UNIQUE(interview_id,interviewer_id))""")
    op.execute(f"""CREATE TABLE interview_scores ({AUDIT}, feedback_id uuid NOT NULL REFERENCES interview_feedback(id) ON DELETE CASCADE, category varchar(50) NOT NULL, score integer NOT NULL CHECK(score BETWEEN 1 AND 10), comments text, UNIQUE(feedback_id,category))""")
    op.execute(f"""CREATE TABLE interview_schedule_history ({AUDIT}, interview_id uuid NOT NULL REFERENCES interviews(id) ON DELETE CASCADE, action varchar(50) NOT NULL, previous_starts_at timestamptz, previous_ends_at timestamptz, new_starts_at timestamptz, new_ends_at timestamptz, comments text)""")
    op.execute(f"""CREATE TABLE interview_attachments ({AUDIT}, interview_id uuid NOT NULL REFERENCES interviews(id) ON DELETE CASCADE, document_id uuid NOT NULL REFERENCES documents(id), attachment_kind varchar(40) NOT NULL, UNIQUE(interview_id,document_id))""")
    for table, columns in (("interviews", "starts_at,status"), ("interviews", "candidate_id,starts_at"), ("interview_panels", "employee_id,interview_id"), ("interview_feedback", "interview_id,interviewer_id"), ("interview_scores", "feedback_id"), ("interview_schedule_history", "interview_id"), ("interview_attachments", "interview_id")):
        op.execute(f"CREATE INDEX ix_{table}_{columns.replace(',', '_')} ON {table}({columns})")


def downgrade() -> None:
    for table in ("interview_attachments", "interview_schedule_history", "interview_scores", "interview_feedback", "interview_panels", "interviews"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE interviews_code_seq")

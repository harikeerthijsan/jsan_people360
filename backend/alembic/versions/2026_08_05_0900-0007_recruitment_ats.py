"""Recruitment and applicant tracking system.

Revision ID: 0007_recruitment_ats
Revises: 0006_job_requisitions
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007_recruitment_ats"
down_revision: str | None = "0006_job_requisitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT = """id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now(),
updated_at timestamptz NOT NULL DEFAULT now(), created_by uuid REFERENCES users(id) ON DELETE SET NULL,
updated_by uuid REFERENCES users(id) ON DELETE SET NULL, deleted_at timestamptz, deleted_by uuid REFERENCES users(id) ON DELETE SET NULL"""

SOURCES = ("Career Portal", "Referral", "LinkedIn", "Naukri", "Indeed", "Employee Referral", "Consultancy", "Walk-In", "Internal Transfer", "Other")
STAGES = ("Applied", "Screening", "HR Interview", "Technical Round 1", "Technical Round 2", "Manager Round", "Client Round", "Selected", "Offer Released", "Offer Accepted", "Joining Pending", "Joined", "Rejected", "Withdrawn")


def upgrade() -> None:
    op.execute("CREATE SEQUENCE job_openings_code_seq AS bigint START WITH 1")
    op.execute("CREATE SEQUENCE candidates_code_seq AS bigint START WITH 1")
    op.execute(f"""CREATE TABLE candidate_sources ({AUDIT}, name varchar(100) NOT NULL UNIQUE, is_active boolean NOT NULL DEFAULT true)""")
    op.execute(f"""CREATE TABLE recruitment_stages ({AUDIT}, name varchar(100) NOT NULL UNIQUE, sequence integer NOT NULL UNIQUE, category varchar(30) NOT NULL DEFAULT 'active', is_active boolean NOT NULL DEFAULT true)""")
    op.execute(f"""CREATE TABLE job_openings ({AUDIT}, job_code varchar(20) NOT NULL UNIQUE DEFAULT 'JOB-' || lpad(nextval('job_openings_code_seq')::text,6,'0'), requisition_id uuid NOT NULL UNIQUE REFERENCES job_requisitions(id), recruiter_id uuid REFERENCES users(id) ON DELETE SET NULL, status varchar(20) NOT NULL DEFAULT 'draft', closing_date date, published_at timestamptz, closed_at timestamptz)""")
    op.execute(f"""CREATE TABLE candidates ({AUDIT}, candidate_code varchar(20) NOT NULL UNIQUE DEFAULT 'CAN-' || lpad(nextval('candidates_code_seq')::text,6,'0'), job_opening_id uuid NOT NULL REFERENCES job_openings(id), source_id uuid NOT NULL REFERENCES candidate_sources(id), stage_id uuid NOT NULL REFERENCES recruitment_stages(id), recruiter_id uuid REFERENCES users(id) ON DELETE SET NULL, first_name varchar(100) NOT NULL, last_name varchar(100) NOT NULL, email varchar(320) NOT NULL, mobile_number varchar(30) NOT NULL, linkedin_url varchar(500), current_company varchar(200), current_designation varchar(200), experience_years numeric(4,1) NOT NULL DEFAULT 0 CHECK(experience_years >= 0), current_ctc numeric(14,2) CHECK(current_ctc >= 0), expected_ctc numeric(14,2) CHECK(expected_ctc >= 0), notice_period_days integer NOT NULL DEFAULT 0 CHECK(notice_period_days BETWEEN 0 AND 365), current_location varchar(200), preferred_location varchar(200), certifications text, tags text, applied_at timestamptz NOT NULL DEFAULT now(), hired_at timestamptz)""")
    op.execute(f"""CREATE TABLE candidate_documents ({AUDIT}, candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, document_id uuid NOT NULL REFERENCES documents(id), document_kind varchar(30) NOT NULL, UNIQUE(candidate_id,document_id))""")
    op.execute(f"""CREATE TABLE candidate_skills ({AUDIT}, candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, name varchar(100) NOT NULL, proficiency varchar(30), UNIQUE(candidate_id,name))""")
    op.execute(f"""CREATE TABLE candidate_stage_history ({AUDIT}, candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, from_stage_id uuid REFERENCES recruitment_stages(id), to_stage_id uuid NOT NULL REFERENCES recruitment_stages(id), comments text)""")
    op.execute(f"""CREATE TABLE recruiter_notes ({AUDIT}, candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, body text NOT NULL, mentions text, is_internal boolean NOT NULL DEFAULT true)""")
    op.execute(f"""CREATE TABLE talent_pools ({AUDIT}, name varchar(150) NOT NULL UNIQUE, description text)""")
    op.execute(f"""CREATE TABLE candidate_talent_pools ({AUDIT}, candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, talent_pool_id uuid NOT NULL REFERENCES talent_pools(id) ON DELETE CASCADE, UNIQUE(candidate_id,talent_pool_id))""")
    for table, columns in (("job_openings", "status,recruiter_id"), ("candidates", "stage_id,recruiter_id"), ("candidate_documents", "candidate_id"), ("candidate_skills", "candidate_id"), ("candidate_stage_history", "candidate_id"), ("recruiter_notes", "candidate_id"), ("candidate_talent_pools", "talent_pool_id,candidate_id")):
        op.execute(f"CREATE INDEX ix_{table}_ats ON {table}({columns})")
    for source in SOURCES:
        op.execute(f"INSERT INTO candidate_sources(name) VALUES ('{source}')")
    for sequence, stage in enumerate(STAGES, 1):
        category = "hired" if stage == "Joined" else "terminal" if stage in {"Rejected", "Withdrawn"} else "active"
        op.execute(f"INSERT INTO recruitment_stages(name,sequence,category) VALUES ('{stage}',{sequence},'{category}')")


def downgrade() -> None:
    for table in ("candidate_talent_pools", "talent_pools", "recruiter_notes", "candidate_stage_history", "candidate_skills", "candidate_documents", "candidates", "job_openings", "recruitment_stages", "candidate_sources"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE candidates_code_seq")
    op.execute("DROP SEQUENCE job_openings_code_seq")

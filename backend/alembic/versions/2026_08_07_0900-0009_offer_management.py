"""Offer management. Revision ID: 0009_offer_management. Revises: 0008_interview_management."""
from collections.abc import Sequence
from alembic import op
revision: str = "0009_offer_management"
down_revision: str | None = "0008_interview_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
AUDIT="""id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),created_by uuid REFERENCES users(id) ON DELETE SET NULL,updated_by uuid REFERENCES users(id) ON DELETE SET NULL,deleted_at timestamptz,deleted_by uuid REFERENCES users(id) ON DELETE SET NULL"""
def upgrade()->None:
 op.execute("CREATE SEQUENCE offers_code_seq AS bigint START WITH 1")
 op.execute(f"CREATE TABLE offer_templates ({AUDIT},name varchar(150) NOT NULL UNIQUE,body text NOT NULL,is_active boolean NOT NULL DEFAULT true)")
 op.execute(f"""CREATE TABLE offers ({AUDIT},offer_code varchar(20) NOT NULL UNIQUE DEFAULT 'OFF-'||lpad(nextval('offers_code_seq')::text,6,'0'),candidate_id uuid NOT NULL REFERENCES candidates(id),job_opening_id uuid NOT NULL REFERENCES job_openings(id),template_id uuid REFERENCES offer_templates(id) ON DELETE SET NULL,status varchar(30) NOT NULL DEFAULT 'draft',ctc numeric(14,2) NOT NULL CHECK(ctc>0),joining_date date NOT NULL,probation_months integer NOT NULL CHECK(probation_months>=0),notice_period_days integer NOT NULL CHECK(notice_period_days>=0),reporting_manager_id uuid REFERENCES employees(id) ON DELETE SET NULL,work_mode varchar(20) NOT NULL,shift varchar(100),benefits text NOT NULL,leave_policy_summary text NOT NULL,working_hours text NOT NULL,confidentiality text NOT NULL,nda_required boolean NOT NULL DEFAULT false,additional_conditions text,release_date date,expiry_date date NOT NULL,accepted_at timestamptz,declined_at timestamptz,decline_reason text,clarification_request text,withdrawn_at timestamptz,withdrawal_reason text,current_version integer NOT NULL DEFAULT 1)""")
 op.execute(f"CREATE TABLE offer_versions ({AUDIT},offer_id uuid NOT NULL REFERENCES offers(id) ON DELETE CASCADE,version_number integer NOT NULL,snapshot jsonb NOT NULL,pdf_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,UNIQUE(offer_id,version_number))")
 op.execute(f"CREATE TABLE offer_approvals ({AUDIT},offer_id uuid NOT NULL REFERENCES offers(id) ON DELETE CASCADE,sequence integer NOT NULL,role_name varchar(100) NOT NULL,approver_id uuid NOT NULL REFERENCES users(id),status varchar(30) NOT NULL DEFAULT 'waiting',comments text,acted_at timestamptz,UNIQUE(offer_id,sequence))")
 op.execute(f"CREATE TABLE offer_status_history ({AUDIT},offer_id uuid NOT NULL REFERENCES offers(id) ON DELETE CASCADE,action varchar(50) NOT NULL,from_status varchar(30),to_status varchar(30) NOT NULL,comments text)")
 op.execute(f"CREATE TABLE offer_salary_components ({AUDIT},offer_id uuid NOT NULL REFERENCES offers(id) ON DELETE CASCADE,name varchar(100) NOT NULL,component_type varchar(30) NOT NULL,annual_amount numeric(14,2) NOT NULL CHECK(annual_amount>=0),is_employer_contribution boolean NOT NULL DEFAULT false,UNIQUE(offer_id,name))")
 for t in ("offer_versions","offer_approvals","offer_status_history","offer_salary_components"): op.execute(f"CREATE INDEX ix_{t}_offer_id ON {t}(offer_id)")
 op.execute("CREATE INDEX ix_offers_status_expiry ON offers(status,expiry_date)")
def downgrade()->None:
 for t in ("offer_salary_components","offer_status_history","offer_approvals","offer_versions","offers","offer_templates"): op.execute(f"DROP TABLE {t}")
 op.execute("DROP SEQUENCE offers_code_seq")

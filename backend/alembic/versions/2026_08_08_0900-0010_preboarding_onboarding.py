"""Preboarding and onboarding. Revision ID: 0010_preboarding_onboarding."""
from collections.abc import Sequence
from alembic import op

revision: str = "0010_preboarding_onboarding"
down_revision: str | None = "0009_offer_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
AUDIT = """id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),created_by uuid REFERENCES users(id) ON DELETE SET NULL,updated_by uuid REFERENCES users(id) ON DELETE SET NULL,deleted_at timestamptz,deleted_by uuid REFERENCES users(id) ON DELETE SET NULL"""


def upgrade() -> None:
    op.execute(f"""CREATE TABLE preboarding_profiles ({AUDIT},candidate_id uuid NOT NULL UNIQUE REFERENCES candidates(id),offer_id uuid NOT NULL UNIQUE REFERENCES offers(id),user_id uuid REFERENCES users(id),joining_date date NOT NULL,joining_confirmed boolean NOT NULL DEFAULT false,first_name varchar(100) NOT NULL,last_name varchar(100) NOT NULL,date_of_birth date,gender varchar(20),blood_group varchar(3),marital_status varchar(20),nationality varchar(100),personal_email varchar(320) NOT NULL,mobile_number varchar(32) NOT NULL,emergency_contact jsonb NOT NULL DEFAULT '{{}}',addresses jsonb NOT NULL DEFAULT '[]',bank_details jsonb NOT NULL DEFAULT '{{}}',aadhaar_number varchar(12),pan_number varchar(10),status varchar(30) NOT NULL DEFAULT 'information_pending',information_approved boolean NOT NULL DEFAULT false,employee_id uuid REFERENCES employees(id))""")
    op.execute(f"""CREATE TABLE onboarding_cases ({AUDIT},profile_id uuid NOT NULL UNIQUE REFERENCES preboarding_profiles(id),employee_id uuid NOT NULL UNIQUE REFERENCES employees(id),status varchar(30) NOT NULL DEFAULT 'not_started',progress_percent integer NOT NULL DEFAULT 0 CHECK(progress_percent BETWEEN 0 AND 100),started_at timestamptz,completed_at timestamptz)""")
    op.execute(f"""CREATE TABLE onboarding_tasks ({AUDIT},case_id uuid NOT NULL REFERENCES onboarding_cases(id) ON DELETE CASCADE,category varchar(30) NOT NULL,title varchar(200) NOT NULL,owner_id uuid NOT NULL REFERENCES users(id),due_date date NOT NULL,status varchar(30) NOT NULL DEFAULT 'not_started',comments text,completed_at timestamptz)""")
    op.execute(f"""CREATE TABLE policy_acknowledgements ({AUDIT},profile_id uuid NOT NULL REFERENCES preboarding_profiles(id) ON DELETE CASCADE,policy_code varchar(50) NOT NULL,policy_name varchar(150) NOT NULL,acknowledged_at timestamptz NOT NULL,ip_address varchar(64),user_agent varchar(500),UNIQUE(profile_id,policy_code))""")
    op.execute(f"""CREATE TABLE onboarding_history ({AUDIT},profile_id uuid NOT NULL REFERENCES preboarding_profiles(id) ON DELETE CASCADE,case_id uuid REFERENCES onboarding_cases(id) ON DELETE CASCADE,action varchar(80) NOT NULL,details text)""")
    for sql in ("CREATE INDEX ix_preboarding_profiles_status ON preboarding_profiles(status)","CREATE INDEX ix_onboarding_cases_status ON onboarding_cases(status)","CREATE INDEX ix_onboarding_tasks_case_id ON onboarding_tasks(case_id)","CREATE INDEX ix_onboarding_tasks_owner_status ON onboarding_tasks(owner_id,status)","CREATE INDEX ix_onboarding_history_profile_id ON onboarding_history(profile_id)"):
        op.execute(sql)


def downgrade() -> None:
    for table in ("onboarding_history", "policy_acknowledgements", "onboarding_tasks", "onboarding_cases", "preboarding_profiles"):
        op.execute(f"DROP TABLE {table}")

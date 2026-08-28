"""Project and client allocations. Revision ID: 0011_project_allocations."""
from collections.abc import Sequence
from alembic import op

revision: str = "0011_project_allocations"
down_revision: str | None = "0010_preboarding_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
AUDIT = """id uuid PRIMARY KEY DEFAULT gen_random_uuid(),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),created_by uuid REFERENCES users(id) ON DELETE SET NULL,updated_by uuid REFERENCES users(id) ON DELETE SET NULL,deleted_at timestamptz,deleted_by uuid REFERENCES users(id) ON DELETE SET NULL"""


def upgrade() -> None:
    op.execute("CREATE SEQUENCE clients_code_seq AS bigint START WITH 1")
    op.execute("CREATE SEQUENCE projects_code_seq AS bigint START WITH 1")
    op.execute(f"""CREATE TABLE clients ({AUDIT},client_code varchar(20) NOT NULL UNIQUE DEFAULT 'CLT-'||lpad(nextval('clients_code_seq')::text,6,'0'),client_name varchar(200) NOT NULL UNIQUE,company_name varchar(200) NOT NULL,industry varchar(100) NOT NULL,contact_person varchar(150) NOT NULL,email varchar(320) NOT NULL,phone varchar(32) NOT NULL,country varchar(100) NOT NULL,address text NOT NULL,website varchar(500),status varchar(20) NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')))""")
    op.execute(f"""CREATE TABLE projects ({AUDIT},project_code varchar(20) NOT NULL UNIQUE DEFAULT 'PRJ-'||lpad(nextval('projects_code_seq')::text,6,'0'),project_name varchar(200) NOT NULL,client_id uuid NOT NULL REFERENCES clients(id),description text NOT NULL,start_date date NOT NULL,end_date date,status varchar(20) NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','active','on_hold','completed','cancelled')),project_manager_id uuid NOT NULL REFERENCES employees(id),delivery_manager_id uuid REFERENCES employees(id),department_id uuid REFERENCES departments(id),practice_id uuid REFERENCES practices(id),work_location_id uuid REFERENCES locations(id),is_billable boolean NOT NULL DEFAULT true,technology_stack jsonb NOT NULL DEFAULT '[]',priority varchar(20) NOT NULL DEFAULT 'medium' CHECK(priority IN ('low','medium','high','critical')),CHECK(end_date IS NULL OR end_date>=start_date))""")
    op.execute(f"""CREATE TABLE project_members ({AUDIT},project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,employee_id uuid NOT NULL REFERENCES employees(id),role varchar(150) NOT NULL,reporting_manager_id uuid REFERENCES employees(id),joined_at date NOT NULL,left_at date,UNIQUE(project_id,employee_id))""")
    op.execute(f"""CREATE TABLE employee_allocations ({AUDIT},employee_id uuid NOT NULL REFERENCES employees(id),project_id uuid NOT NULL REFERENCES projects(id),member_id uuid NOT NULL REFERENCES project_members(id),allocation_percentage numeric(5,2) NOT NULL CHECK(allocation_percentage>0 AND allocation_percentage<=100),start_date date NOT NULL,end_date date,billable boolean NOT NULL DEFAULT true,status varchar(20) NOT NULL DEFAULT 'active',reason text,CHECK(end_date IS NULL OR end_date>=start_date))""")
    op.execute(f"""CREATE TABLE allocation_history ({AUDIT},employee_id uuid NOT NULL REFERENCES employees(id),previous_project_id uuid REFERENCES projects(id),new_project_id uuid REFERENCES projects(id),previous_allocation_percentage numeric(5,2),new_allocation_percentage numeric(5,2),effective_date date NOT NULL,reason text NOT NULL,action varchar(30) NOT NULL)""")
    for sql in ("CREATE INDEX ix_clients_status ON clients(status)","CREATE INDEX ix_projects_status_end_date ON projects(status,end_date)","CREATE INDEX ix_project_members_project ON project_members(project_id)","CREATE INDEX ix_project_members_employee ON project_members(employee_id)","CREATE INDEX ix_allocations_employee_dates ON employee_allocations(employee_id,start_date,end_date)","CREATE INDEX ix_allocations_project ON employee_allocations(project_id)","CREATE INDEX ix_allocation_history_employee ON allocation_history(employee_id)"):
        op.execute(sql)


def downgrade() -> None:
    for table in ("allocation_history", "employee_allocations", "project_members", "projects", "clients"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SEQUENCE projects_code_seq")
    op.execute("DROP SEQUENCE clients_code_seq")

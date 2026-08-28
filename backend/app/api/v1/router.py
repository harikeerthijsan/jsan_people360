"""API v1 aggregate router.

Future feature modules register here and nowhere else::

    from app.api.v1.routes import attendance
    api_router.include_router(attendance.router)
"""

from fastapi import APIRouter

from app.api.v1.routes import (
    app_settings,
    assets,
    audit,
    auth,
    document_masters,
    documents,
    employees,
    health,
    helpdesk,
    hr,
    interviews,
    manager,
    offboarding,
    offers,
    onboarding,
    organization,
    payroll,
    payroll_reports,
    performance,
    projects,
    rbac,
    recruitment,
    requisitions,
    self_service,
    users,
    workforce,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organization.router)
api_router.include_router(employees.router)
api_router.include_router(documents.router)
api_router.include_router(document_masters.router)
api_router.include_router(requisitions.router)
api_router.include_router(requisitions.notification_router)
api_router.include_router(recruitment.router)
api_router.include_router(interviews.router)
api_router.include_router(offers.router)
api_router.include_router(onboarding.router)
api_router.include_router(performance.router)
api_router.include_router(projects.router)
api_router.include_router(workforce.router)
api_router.include_router(assets.router)
api_router.include_router(payroll.router)
api_router.include_router(payroll_reports.router)
api_router.include_router(app_settings.router)
api_router.include_router(audit.router)
api_router.include_router(helpdesk.router)
api_router.include_router(helpdesk.announcements_router)
api_router.include_router(offboarding.router)
api_router.include_router(rbac.router)
api_router.include_router(rbac.assignment_router)
# Last, and deliberately: ``/me`` and ``/manager`` are views onto the modules
# above rather than modules of their own, so they are registered once those all
# exist. ``/me`` answers "what is mine" and ``/manager`` answers "what is my
# team's"; both are compositions, and neither owns a rule.
api_router.include_router(self_service.router)
api_router.include_router(manager.router)
api_router.include_router(assets.me_router)
api_router.include_router(payroll.me_router)
api_router.include_router(payroll_reports.me_router)
api_router.include_router(helpdesk.me_router)
api_router.include_router(assets.manager_router)
api_router.include_router(assets.hr_router)
api_router.include_router(offboarding.me_router)
api_router.include_router(offboarding.manager_router)
api_router.include_router(hr.router)

__all__ = ["api_router"]

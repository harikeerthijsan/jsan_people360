from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.location import Location

BASE = f"{settings.API_V1_PREFIX}/projects"


async def test_client_project_allocation_capacity_and_history(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    employee: Employee,
    location: Location,
):
    created_client = await client.post(
        f"{BASE}/clients",
        json={
            "client_name": "Acme Delivery",
            "company_name": "Acme Corporation",
            "industry": "Technology",
            "contact_person": "Jane Doe",
            "email": "jane@acme.example",
            "phone": "9876543210",
            "country": "India",
            "address": "1 Business Park",
            "website": "https://acme.example",
            "status": "active",
        },
        headers=auth_headers,
    )
    assert created_client.status_code == 201, created_client.text
    client_id = created_client.json()["data"]["id"]
    assert created_client.json()["data"]["client_code"].startswith("CLT-")
    project_ids = []
    for name in ("Platform Modernization", "Cloud Migration"):
        response = await client.post(
            BASE,
            json={
                "project_name": name,
                "client_id": client_id,
                "description": "Enterprise delivery project",
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=90)),
                "status": "active",
                "project_manager_id": str(employee.id),
                "work_location_id": str(location.id),
                "is_billable": True,
                "technology_stack": ["Python"],
                "priority": "high",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["project_code"].startswith("PRJ-")
        project_ids.append(response.json()["data"]["id"])

    def allocation(percent):
        return {
            "employee_id": str(employee.id),
            "role": "Senior Engineer",
            "allocation_percentage": percent,
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=60)),
            "billable": True,
            "reason": "Client delivery",
        }

    first = await client.post(
        f"{BASE}/{project_ids[0]}/allocations", json=allocation(75), headers=auth_headers
    )
    assert first.status_code == 201, first.text
    conflict = await client.post(
        f"{BASE}/{project_ids[1]}/allocations", json=allocation(30), headers=auth_headers
    )
    assert conflict.status_code == 409
    second = await client.post(
        f"{BASE}/{project_ids[1]}/allocations", json=allocation(25), headers=auth_headers
    )
    assert second.status_code == 201, second.text
    removed = await client.post(
        f"{BASE}/allocations/{second.json()['data']['id']}/remove",
        json={"effective_date": str(date.today()), "reason": "Reallocated to primary project"},
        headers=auth_headers,
    )
    assert removed.status_code == 200, removed.text
    changed = await client.post(
        f"{BASE}/allocations/{first.json()['data']['id']}/change",
        json={
            "allocation_percentage": 90,
            "effective_date": str(date.today() + timedelta(days=1)),
            "end_date": str(date.today() + timedelta(days=60)),
            "billable": True,
            "reason": "Increased delivery demand",
        },
        headers=auth_headers,
    )
    assert changed.status_code == 200, changed.text
    history = await client.get(f"{BASE}/employees/{employee.id}/allocation-history", headers=auth_headers)
    assert history.status_code == 200
    assert len(history.json()["data"]) == 4
    dashboard = await client.get(f"{BASE}/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["data"]["allocation_conflicts"] == 0


async def test_project_dashboard_requires_authentication(client: AsyncClient):
    assert (await client.get(f"{BASE}/dashboard")).status_code == 401

from fastapi.testclient import TestClient
import pytest

from app.integrations.calendar import CalendarConnectorConfig, GoogleCalendarConnector
from app.main import app
from app.security.paths import require_project_subpath


def test_connector_paths_cannot_escape_secret_or_data_directories():
    with pytest.raises(ValueError):
        require_project_subpath("outside.json", "secrets", "credential")
    with pytest.raises(ValueError):
        GoogleCalendarConnector(CalendarConnectorConfig(
            credentials_path="secrets/google_calendar_credentials.json",
            token_path="secrets/not-a-token.json",
        ))


def test_schedule_explanation_lock_and_preview_proposal_are_backward_safe():
    client = TestClient(app)
    user_id = "roadmap-safety-user"
    created = client.post("/v1/workflow/plan", json={
        "user_id": user_id,
        "task_inputs": [{"title": "Học toán", "estimated_minutes": 45}],
    })
    assert created.status_code == 200
    plan = created.json()
    block = next(item for item in plan["schedule"] if item["block_type"] == "task")
    assert block["explanation"]["why_this_slot"]
    assert block["is_locked"] is False

    locked = client.post(
        f"/v1/schedule/{plan['plan_id']}/blocks/{block['block_id']}/lock?user_id={user_id}",
        json={"locked": True, "reason": "Giữ giờ học"},
    )
    assert locked.status_code == 200
    assert next(item for item in locked.json()["schedule"] if item["block_id"] == block["block_id"])["is_locked"]

    proposal = client.post("/v1/workflow/proposals/recalculate", json={
        "user_id": user_id,
        "trigger": "progress_delay",
    })
    assert proposal.status_code == 200
    assert proposal.json()["requires_confirmation"] is True
    assert proposal.json()["risk"] == "high"
    assert proposal.json()["applied"] is False

    analytics = client.get(f"/v1/analytics/productivity?user_id={user_id}")
    assert analytics.status_code == 200
    assert "duration_mae_minutes" in analytics.json()["metrics"]

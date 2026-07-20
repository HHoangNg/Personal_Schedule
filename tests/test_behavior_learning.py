import json
import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import app
from app.schemas import WorkflowRequest
from app.storage.repository import PlanRepository
from app.workflow.calendar_workflow import CalendarWorkflow


def test_block_status_and_daily_feedback_feed_analytics():
    client = TestClient(app)
    user_id = "behavior-learning-user"
    created = client.post(
        "/v1/workflow/plan",
        json={"user_id": user_id, "task_inputs": [{"title": "Học toán", "estimated_minutes": 30}]},
    )
    assert created.status_code == 200
    plan = created.json()
    block = next(item for item in plan["schedule"] if item["task_title"] == "Học toán")

    updated = client.post(
        f"/v1/schedule/{plan['plan_id']}/blocks/{block['block_id']}/status?user_id={user_id}",
        json={"status": "completed", "actual_minutes": 35},
    )
    assert updated.status_code == 200
    updated_block = next(item for item in updated.json()["schedule"] if item["block_id"] == block["block_id"])
    assert updated_block["status"] == "completed"

    feedback = client.post(
        "/v1/feedback/daily",
        json={
            "user_id": user_id,
            "feedback_date": date.today().isoformat(),
            "energy": 5,
            "focus": 4,
            "effective_period": "morning",
            "schedule_feeling": "balanced",
            "procrastinated_tasks": [],
            "note": "Buổi sáng tập trung tốt.",
        },
    )
    assert feedback.status_code == 200

    analytics = client.get(f"/v1/analytics/productivity?user_id={user_id}")
    assert analytics.status_code == 200
    assert analytics.json()["profile"]["completion_rate"] == 1.0
    assert analytics.json()["profile"]["effective_period"] == "morning"


def test_recalculate_keeps_same_plan_id():
    client = TestClient(app)
    user_id = "recalculate-user"
    first = client.post("/v1/workflow/plan", json={"user_id": user_id, "raw_input": "Đọc sách"}).json()
    response = client.post("/v1/workflow/recalculate", json={"user_id": user_id})
    assert response.status_code == 200
    assert response.json()["plan_id"] == first["plan_id"]


def test_legacy_schedule_blocks_get_stable_ids_before_status_update(tmp_path):
    database_path = tmp_path / "plans.db"
    settings = Settings(llm_provider="mock", database_path=str(database_path))
    repo = PlanRepository(str(database_path))
    user_id = "legacy-block-user"
    saved = repo.save(
        user_id,
        CalendarWorkflow(settings).run(WorkflowRequest(user_id=user_id, raw_input="study math")),
    )

    payload = saved.model_dump(mode="json")
    for block in payload["schedule"]:
        block.pop("block_id", None)
        block.pop("status", None)
    legacy_json = json.dumps(payload, ensure_ascii=False)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE plans SET payload_json = ? WHERE user_id = ? AND plan_id = ?",
            (legacy_json, user_id, saved.plan_id),
        )
    (database_path.parent / "plans" / f"{saved.plan_id}.json").write_text(
        legacy_json, encoding="utf-8"
    )

    first_load = repo.get_for_user(user_id, saved.plan_id)
    second_load = repo.get_for_user(user_id, saved.plan_id)
    block = next(item for item in first_load.schedule if item.block_type == "task")

    assert block.block_id == next(
        item.block_id for item in second_load.schedule if item.task_title == block.task_title
    )
    updated, _ = repo.update_block_status(user_id, saved.plan_id, block.block_id, "completed", 30)
    assert next(item for item in updated.schedule if item.block_id == block.block_id).status == "completed"

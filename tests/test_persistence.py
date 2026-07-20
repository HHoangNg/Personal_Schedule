import json

from app.core.settings import Settings
from app.schemas import WorkflowRequest
from app.storage.repository import PlanRepository
from app.workflow.personalized_service import PersonalizedProductivityWorkflow


def test_saved_plan_survives_a_new_repository_instance(tmp_path):
    database_path = tmp_path / "plans.db"
    workflow = PersonalizedProductivityWorkflow(
        Settings(llm_provider="mock", database_path=str(database_path))
    )
    request = WorkflowRequest(
        user_id="minh",
        raw_input="Học toán và đọc truyện",
        deadline_at="2026-07-20T21:00:00",
        daily_start_time="19:00",
        daily_end_time="21:00",
        focus_minutes=25,
    )

    saved = PlanRepository(str(database_path)).save(request.user_id, workflow.run(request))
    reloaded = PlanRepository(str(database_path)).get_for_user(request.user_id, saved.plan_id)

    assert saved.plan_id
    assert reloaded is not None
    assert reloaded.plan_id == saved.plan_id
    assert reloaded.tasks[0].deadline.isoformat() == "2026-07-20"
    assert reloaded.schedule
    assert reloaded.plan_input is not None
    assert (database_path.parent / "plans" / f"{saved.plan_id}.json").exists()


def test_saved_plan_payload_is_mirrored_to_qdrant(monkeypatch, tmp_path):
    captured = {}

    class FakeQdrantMemory:
        def __init__(self, url, collection, vector_name="dense", api_key=None):
            captured["url"] = url
            captured["collection"] = collection
            captured["vector_name"] = vector_name
            captured["qdrant_api_key"] = api_key

        def ensure_collection(self, vector_size=768):
            captured["vector_size"] = vector_size

        def upsert(self, point_id, vector, payload):
            captured["point_id"] = point_id
            captured["vector"] = vector
            captured["payload"] = payload

    class FakeVoyageEmbedder:
        def __init__(self, api_key, model):
            captured["voyage_api_key"] = api_key
            captured["voyage_model"] = model

        def embed(self, text):
            captured["embedded_text"] = text
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr("app.storage.repository.QdrantMemory", FakeQdrantMemory)
    monkeypatch.setattr("app.storage.repository.VoyageEmbedder", FakeVoyageEmbedder)
    database_path = tmp_path / "plans.db"
    workflow = PersonalizedProductivityWorkflow(
        Settings(llm_provider="mock", database_path=str(database_path))
    )
    request = WorkflowRequest(user_id="qdrant-user", raw_input="Hoc tieng Anh")

    saved = PlanRepository(
        str(database_path),
        qdrant_url="http://localhost:6333",
        qdrant_api_key="qdrant-key",
        qdrant_collection="personal_productivity_memory",
        qdrant_vector_size=3,
        qdrant_vector_name="dense",
        qdrant_sync_enabled=True,
        voyage_api_key="voyage-key",
        voyage_model="voyage-3",
    ).save(request.user_id, workflow.run(request))
    json_payload = json.loads(
        (database_path.parent / "plans" / f"{saved.plan_id}.json").read_text(encoding="utf-8")
    )

    assert captured["point_id"] == saved.plan_id
    assert captured["collection"] == "personal_productivity_memory"
    assert captured["vector_name"] == "dense"
    assert captured["qdrant_api_key"] == "qdrant-key"
    assert captured["voyage_api_key"] == "voyage-key"
    assert captured["voyage_model"] == "voyage-3"
    assert captured["vector"] == [0.1, 0.2, 0.3]
    assert captured["payload"] == json_payload
    assert json.loads(captured["embedded_text"]) == json_payload

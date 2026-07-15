from app.core.settings import Settings
from app.schemas import TaskInput, WorkflowRequest
from app.workflow.calendar_workflow import CalendarWorkflow


class BrokenProvider:
    def generate_json(self, prompt, schema):
        raise RuntimeError("503 UNAVAILABLE")


def test_additional_information_creates_three_daily_meal_blocks():
    request = WorkflowRequest(
        user_id="calendar-test",
        task_inputs=[TaskInput(title="Nấu cơm", estimated_minutes=30)],
        planning_notes="Nấu cơm 3 bữa mỗi ngày",
    )
    result = CalendarWorkflow(Settings(llm_provider="mock")).run(request)
    cooking = [item for item in result.schedule if item.task_title == "Nấu cơm"]

    assert len({item.date for item in cooking}) == 14
    assert all(item.minutes == 30 for item in cooking)
    assert len(cooking) == 42


def test_calendar_still_updates_when_llm_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.workflow.calendar_workflow.build_provider", lambda settings: BrokenProvider())
    request = WorkflowRequest(
        user_id="fallback-user",
        task_inputs=[TaskInput(title="Há»c tiáº¿ng Anh", estimated_minutes=60)],
    )

    result = CalendarWorkflow(Settings(llm_provider="gemini", gemini_api_key="fake")).run(request)

    assert result.llm_provider == "local-fallback"
    assert result.tasks[0].title == "Há»c tiáº¿ng Anh"
    assert any(block.task_title == "Há»c tiáº¿ng Anh" for block in result.schedule)
    assert any("LLM" in warning for warning in result.warnings)

from datetime import date, datetime, time, timedelta

from app.llm.providers import build_provider
from app.reliability.guardrails import confidence, validate_grounding, validate_schedule
from app.schemas import ScheduleSession, Subtask, Task, WorkflowRequest, WorkflowResult


TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "deadline": {
                        "type": "string",
                        "nullable": True,
                        "description": "YYYY-MM-DD if explicitly stated, otherwise null.",
                    },
                    "deadline_source": {
                        "type": "string",
                        "nullable": True,
                        "description": "Exact phrase that supports the deadline, otherwise null.",
                    },
                    "type": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "estimated_minutes": {"type": "integer", "minimum": 5, "maximum": 480},
                },
                "required": [
                    "title",
                    "deadline",
                    "deadline_source",
                    "type",
                    "priority",
                    "estimated_minutes",
                ],
            },
        }
    },
    "required": ["tasks"],
}


class ProductivityWorkflow:
    def __init__(self, settings):
        self.settings = settings
        self.provider = build_provider(settings)

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        llm = self.provider.generate_json(request.raw_input, TASK_SCHEMA)
        raw_tasks = llm.data.get("tasks", [])
        tasks = [Task.model_validate(item) for item in raw_tasks]
        warnings = validate_grounding(tasks, request.raw_input)
        if llm.provider == "mock":
            warnings.append(
                "Đang dùng LLM_PROVIDER=mock nên kết quả chỉ là dữ liệu giả lập, chưa gọi GPT/Gemini."
            )

        priorities = [
            {"task": task.title, "score": self._score(task), "reason": "deadline/goal impact"}
            for task in tasks
        ]
        subtasks = {
            task.title: [
                Subtask(
                    title=f"Bắt đầu: {task.title}",
                    estimated_minutes=min(task.estimated_minutes, 30),
                    definition_of_done="Có artefact kiểm tra được",
                )
            ]
            for task in tasks
        }
        schedule = self._schedule(tasks, request.available_minutes_per_day)
        warnings.extend(
            validate_schedule(
                sum(item.minutes for item in schedule),
                request.available_minutes_per_day * 7,
            )
        )
        return WorkflowResult(
            llm_provider=llm.provider,
            llm_model=self.settings.llm_model,
            llm_raw_preview=llm.raw_text[:500],
            tasks=tasks,
            priorities=priorities,
            subtasks=subtasks,
            schedule=schedule,
            warnings=warnings,
            needs_confirmation=bool(warnings),
            confidence=confidence(warnings, len(tasks)),
        )

    @staticmethod
    def _score(task: Task) -> int:
        return {"high": 85, "medium": 60, "low": 30}[task.priority] + (10 if task.deadline else 0)

    @staticmethod
    def _schedule(tasks: list[Task], daily_limit: int) -> list[ScheduleSession]:
        result, day, remaining, used_today = [], date.today(), daily_limit, 0
        for task in sorted(tasks, key=lambda x: (-ProductivityWorkflow._score(x), x.title)):
            minutes_left = task.estimated_minutes
            while minutes_left > 0:
                if remaining <= 0:
                    day, remaining, used_today = day + timedelta(days=1), daily_limit, 0

                chunk = min(minutes_left, remaining)
                start_at = datetime.combine(day, time(hour=19)) + timedelta(minutes=used_today)
                end_at = start_at + timedelta(minutes=chunk)
                result.append(
                    ScheduleSession(
                        date=day,
                        start_time=start_at.strftime("%H:%M"),
                        end_time=end_at.strftime("%H:%M"),
                        task_title=task.title,
                        minutes=chunk,
                    )
                )
                remaining -= chunk
                used_today += chunk
                minutes_left -= chunk
        return result

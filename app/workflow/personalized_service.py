import json
from datetime import date, datetime, timedelta

from app.llm.providers import build_provider
from app.reliability.guardrails import confidence, validate_grounding, validate_schedule
from app.schemas import (
    FocusSession,
    GoalAnalysis,
    ReviewQuestion,
    Risk,
    ScheduleSession,
    Subtask,
    Task,
    TaskInput,
    WorkflowRequest,
    WorkflowResult,
)


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"}, "deadline": {"type": "string", "nullable": True},
                    "deadline_source": {"type": "string", "nullable": True}, "type": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "estimated_minutes": {"type": "integer", "minimum": 5, "maximum": 480},
                },
                "required": ["title", "deadline", "deadline_source", "type", "priority", "estimated_minutes"],
            },
        },
        "goal_analysis": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "success_criteria": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "success_criteria", "assumptions"],
        },
        "suggested_subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task_title": {"type": "string"}, "title": {"type": "string"},
                    "estimated_minutes": {"type": "integer", "minimum": 5, "maximum": 240},
                    "definition_of_done": {"type": "string"},
                },
                "required": ["task_title", "title", "estimated_minutes", "definition_of_done"],
            },
        },
        "schedule_reasoning": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "mitigation": {"type": "string"},
                },
                "required": ["title", "severity", "mitigation"],
            },
        },
        "focus_sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task_title": {"type": "string"}, "objective": {"type": "string"},
                    "method": {"type": "string"}, "checklist": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_title", "objective", "method", "checklist"],
            },
        },
        "review_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "purpose": {"type": "string"}},
                "required": ["question", "purpose"],
            },
        },
    },
    "required": ["tasks", "goal_analysis", "suggested_subtasks", "schedule_reasoning", "risks", "focus_sessions", "review_questions"],
}


class PersonalizedProductivityWorkflow:
    def __init__(self, settings):
        self.settings = settings
        self.provider = build_provider(settings)

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        llm = self.provider.generate_json(self._planning_context(request), PLAN_SCHEMA)
        data = llm.data
        llm_tasks = [self._validate_task(item) for item in data.get("tasks", [])]
        tasks = self._apply_task_inputs(llm_tasks, request.task_inputs)
        if request.deadline_at and not request.task_inputs:
            for task in tasks:
                task.deadline = request.deadline_at.date()
                task.deadline_mode = "specific"
                task.deadline_time = request.deadline_at.time()
                task.deadline_source = "Người dùng đã điền deadline riêng"
        grounding_input = request.raw_input
        if request.task_inputs:
            grounding_input = f"{grounding_input} {' '.join(item.deadline_at.date().isoformat() for item in request.task_inputs if item.deadline_at)}"
        if request.deadline_at:
            grounding_input = f"{grounding_input} {request.deadline_at.date().isoformat()}"
        warnings = validate_grounding(tasks, grounding_input)
        if llm.provider == "mock":
            warnings.append("Đang dùng LLM_PROVIDER=mock nên phần phân tích AI chỉ là dữ liệu giả lập.")

        schedule, schedule_warnings = self._schedule_personalized(tasks, request)
        warnings.extend(schedule_warnings)
        warnings.extend(validate_schedule(sum(item.minutes for item in schedule), request.available_minutes_per_day * 7))
        return WorkflowResult(
            llm_provider=llm.provider,
            llm_model=self.settings.llm_model,
            llm_raw_preview=llm.raw_text[:500],
            tasks=tasks,
            priorities=[{"task": task.title, "score": self._score(task), "reason": self._priority_reason(task)} for task in tasks],
            subtasks=self._build_subtasks(tasks, data.get("suggested_subtasks", [])),
            schedule=schedule,
            goal_analysis=GoalAnalysis.model_validate(data.get("goal_analysis", {})),
            schedule_reasoning=data.get("schedule_reasoning", ""),
            risks=[Risk.model_validate(item) for item in data.get("risks", [])],
            focus_sessions=[FocusSession.model_validate(item) for item in data.get("focus_sessions", [])],
            review_questions=[ReviewQuestion.model_validate(item) for item in data.get("review_questions", [])],
            plan_input=request,
            warnings=warnings,
            needs_confirmation=bool(warnings),
            confidence=confidence(warnings, len(tasks)),
        )

    @staticmethod
    def _planning_context(request: WorkflowRequest) -> str:
        task_text = request.raw_input or ", ".join(item.title for item in request.task_inputs)
        return json.dumps(
            {
                "task_text": task_text,
                "structured_tasks": [item.model_dump(mode="json") for item in request.task_inputs],
                "verified_constraints": {
                    "deadline_at": request.deadline_at.isoformat() if request.deadline_at else None,
                    "available_minutes_per_day": request.available_minutes_per_day,
                    "daily_window": f"{request.daily_start_time:%H:%M}-{request.daily_end_time:%H:%M}",
                    "preferred_weekdays": request.preferred_weekdays,
                    "energy_peak": request.energy_peak,
                    "work_style": request.work_style,
                    "focus_minutes": request.focus_minutes,
                    "existing_commitments": request.existing_commitments,
                    "planning_notes": request.planning_notes,
                },
            }, ensure_ascii=False,
        )

    @staticmethod
    def _validate_task(item: dict) -> Task:
        """Accept providers that return an ISO datetime even though Task stores a calendar date."""
        normalized = dict(item)
        deadline = normalized.get("deadline")
        if isinstance(deadline, str) and "T" in deadline:
            normalized["deadline"] = deadline.split("T", maxsplit=1)[0]
        return Task.model_validate(normalized)

    @staticmethod
    def _apply_task_inputs(tasks: list[Task], inputs: list[TaskInput]) -> list[Task]:
        if not inputs:
            return tasks
        by_title = {task.title.casefold(): task for task in tasks}
        result = []
        for item in inputs:
            task = by_title.get(item.title.casefold()) or Task(
                title=item.title,
                type=item.type,
                priority=item.priority,
                estimated_minutes=item.estimated_minutes,
            )
            task.title = item.title
            task.type = item.type
            task.priority = item.priority
            task.estimated_minutes = item.estimated_minutes
            task.deadline_mode = item.deadline_mode
            task.deadline = item.deadline_at.date() if item.deadline_mode == "specific" and item.deadline_at else None
            task.deadline_time = item.deadline_at.time() if item.deadline_mode == "specific" and item.deadline_at else None
            task.deadline_source = "NgÆ°á»i dÃ¹ng Ä‘iá»n trong trÆ°á»ng deadline" if task.deadline else None
            result.append(task)
        return result

    @staticmethod
    def _score(task: Task) -> int:
        return {"high": 85, "medium": 60, "low": 30}[task.priority] + (10 if task.deadline else 0)

    @staticmethod
    def _priority_reason(task: Task) -> str:
        return "Ưu tiên theo deadline đã xác nhận" if task.deadline else "AI đề xuất theo tác động và effort"

    @staticmethod
    def _build_subtasks(tasks: list[Task], suggestions: list[dict]) -> dict[str, list[Subtask]]:
        result = {task.title: [] for task in tasks}
        titles = {task.title.casefold(): task.title for task in tasks}
        for item in suggestions:
            task_title = titles.get(str(item.get("task_title", "")).casefold())
            if task_title:
                result[task_title].append(Subtask.model_validate(item))
        for task in tasks:
            if not result[task.title]:
                result[task.title] = [Subtask(title=f"Bắt đầu: {task.title}", estimated_minutes=min(task.estimated_minutes, 30), definition_of_done="Có artefact hoặc ghi chú để kiểm tra được")]
        return result

    @classmethod
    def _schedule_personalized(cls, tasks: list[Task], request: WorkflowRequest) -> tuple[list[ScheduleSession], list[str]]:
        if request.daily_end_time <= request.daily_start_time:
            return [], ["Giá» káº¿t thÃºc pháº£i sau giá» báº¯t Ä‘áº§u Ä‘á»ƒ AI cÃ³ thá»ƒ xáº¿p lá»‹ch."]
        schedule: list[ScheduleSession] = []
        warnings: list[str] = []
        selected_days = set(request.preferred_weekdays)
        today = date.today()

        def place_on_day(task: Task, day: date) -> bool:
            start_at = datetime.combine(day, request.daily_start_time)
            end_at = datetime.combine(day, request.daily_end_time)
            if request.deadline_at and day == request.deadline_at.date():
                end_at = min(end_at, request.deadline_at)
            if task.deadline and day == task.deadline and request.deadline_at:
                end_at = min(end_at, request.deadline_at)
            if task.deadline and day == task.deadline and task.deadline_time:
                end_at = min(end_at, datetime.combine(day, task.deadline_time))
            capacity = min(request.available_minutes_per_day, int((end_at - start_at).total_seconds() // 60))
            used = sum(item.minutes for item in schedule if item.date == day)
            remaining = capacity - used
            minutes_left = task.estimated_minutes
            while minutes_left > 0 and remaining > 0:
                chunk = min(minutes_left, remaining, request.focus_minutes)
                start = start_at + timedelta(minutes=used)
                end = start + timedelta(minutes=chunk)
                schedule.append(ScheduleSession(date=day, start_time=start.strftime("%H:%M"), end_time=end.strftime("%H:%M"), task_title=task.title, minutes=chunk))
                minutes_left -= chunk
                used += chunk
                remaining -= chunk
            return minutes_left == 0

        for task in sorted(tasks, key=lambda item: (-cls._score(item), item.title)):
            if task.deadline_mode == "daily":
                for offset in range(7):
                    day = today + timedelta(days=offset)
                    if day.weekday() in selected_days and not place_on_day(task, day):
                        warnings.append(f"Không đủ thời gian trong ngày để xếp đủ công việc hằng ngày '{task.title}'.")
                continue

            placed = False
            for offset in range(7):
                day = today + timedelta(days=offset)
                if day.weekday() not in selected_days:
                    continue
                if task.deadline and day > task.deadline:
                    break
                if place_on_day(task, day):
                    placed = True
                    break
            if not placed:
                warnings.append(f"Không đủ khung giờ trước deadline để xếp hết '{task.title}'.")
        return schedule, warnings

    @classmethod
    def _schedule(cls, tasks: list[Task], request: WorkflowRequest) -> tuple[list[ScheduleSession], list[str]]:
        if request.daily_end_time <= request.daily_start_time:
            return [], ["Giờ kết thúc phải sau giờ bắt đầu để AI có thể xếp lịch."]
        schedule: list[ScheduleSession] = []
        warnings: list[str] = []
        day = date.today()
        selected_days = set(request.preferred_weekdays)
        for task in sorted(tasks, key=lambda item: (-cls._score(item), item.title)):
            minutes_left = task.estimated_minutes
            while minutes_left > 0:
                if task.deadline and day > task.deadline:
                    warnings.append(f"Không đủ khung giờ trước deadline để xếp hết '{task.title}'.")
                    break
                if day.weekday() not in selected_days:
                    day += timedelta(days=1)
                    continue
                start_at = datetime.combine(day, request.daily_start_time)
                end_at = datetime.combine(day, request.daily_end_time)
                if request.deadline_at and day == request.deadline_at.date():
                    end_at = min(end_at, request.deadline_at)
                capacity = min(request.available_minutes_per_day, int((end_at - start_at).total_seconds() // 60))
                used = sum(item.minutes for item in schedule if item.date == day)
                remaining = capacity - used
                if remaining <= 0:
                    day += timedelta(days=1)
                    continue
                chunk = min(minutes_left, remaining, request.focus_minutes)
                start = start_at + timedelta(minutes=used)
                end = start + timedelta(minutes=chunk)
                schedule.append(ScheduleSession(date=day, start_time=start.strftime("%H:%M"), end_time=end.strftime("%H:%M"), task_title=task.title, minutes=chunk))
                minutes_left -= chunk
        return schedule, warnings

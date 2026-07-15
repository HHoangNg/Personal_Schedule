import copy
import json
import re
from datetime import date, timedelta

from app.llm.providers import StructuredLLMResponse, build_provider
from app.reliability.guardrails import confidence, validate_grounding
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
from app.workflow.personalized_service import PLAN_SCHEMA


CALENDAR_SCHEMA = copy.deepcopy(PLAN_SCHEMA)
CALENDAR_SCHEMA["properties"]["tasks"]["items"]["properties"]["occurrences_per_day"] = {
    "type": "integer", "minimum": 1, "maximum": 6,
}


class CalendarWorkflow:
    """Builds one conflict-aware, 14-day calendar per user."""

    def __init__(self, settings):
        self.settings = settings
        self.provider = build_provider(settings)

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        response, llm_warnings = self._generate_calendar_analysis(request)
        raw_tasks = [self._validate_task(item) for item in response.data.get("tasks", [])]
        tasks = self._apply_inputs(raw_tasks, request.task_inputs, request.planning_notes)
        grounding_text = request.raw_input + " " + " ".join(
            item.deadline_at.date().isoformat() for item in request.task_inputs if item.deadline_at
        )
        warnings = llm_warnings + validate_grounding(tasks, grounding_text)
        if not tasks:
            warnings.append("Chưa có công việc để xếp lịch.")
        if response.provider == "mock":
            warnings.append("Đang dùng LLM_PROVIDER=mock; ưu tiên và loại công việc chỉ là dữ liệu mô phỏng.")
        schedule, schedule_warnings = self._build_calendar(tasks, request)
        warnings.extend(schedule_warnings)
        data = response.data
        return WorkflowResult(
            llm_provider=response.provider,
            llm_model=self._model_label(response.provider),
            llm_raw_preview=response.raw_text[:500],
            tasks=tasks,
            priorities=[{"task": task.title, "score": self._score(task), "reason": self._reason(task)} for task in tasks],
            subtasks=self._subtasks(tasks, data.get("suggested_subtasks", [])),
            schedule=schedule,
            goal_analysis=GoalAnalysis.model_validate(data.get("goal_analysis", {})),
            schedule_reasoning="Lịch 14 ngày được lấp theo ưu tiên AI, thời lượng thực tế và thông tin bổ sung.",
            risks=[Risk.model_validate(item) for item in data.get("risks", [])],
            focus_sessions=[FocusSession.model_validate(item) for item in data.get("focus_sessions", [])],
            review_questions=[ReviewQuestion.model_validate(item) for item in data.get("review_questions", [])],
            plan_input=request,
            warnings=warnings,
            needs_confirmation=bool(warnings),
            confidence=confidence(warnings, len(tasks)),
        )

    def _generate_calendar_analysis(self, request: WorkflowRequest) -> tuple[StructuredLLMResponse, list[str]]:
        try:
            return self.provider.generate_json(self._context(request), CALENDAR_SCHEMA), []
        except Exception as exc:
            response = self._fallback_response(request, exc)
            return response, [
                "LLM đang tạm thời không phản hồi nên hệ thống đã cập nhật lịch bằng bộ xếp lịch cục bộ.",
                f"Lỗi LLM: {type(exc).__name__}: {exc}",
            ]

    def _model_label(self, provider: str) -> str:
        if provider == "openai":
            return self.settings.openai_model
        if provider == "gemini":
            return self.settings.gemini_model
        if provider == "openai+gemini":
            return f"{self.settings.openai_model} + {self.settings.gemini_model}"
        return self.settings.llm_model

    @staticmethod
    def _fallback_response(request: WorkflowRequest, exc: Exception) -> StructuredLLMResponse:
        tasks = [
            {
                "title": CalendarWorkflow._input_title(item),
                "deadline": item.deadline_at.date().isoformat()
                if item.deadline_mode == "specific" and item.deadline_at
                else None,
                "deadline_source": "Deadline do người dùng nhập"
                if item.deadline_mode == "specific" and item.deadline_at
                else None,
                "type": "general",
                "priority": "medium",
                "estimated_minutes": item.estimated_minutes,
                "deadline_mode": item.deadline_mode,
                "occurrences_per_day": 1,
            }
            for item in request.task_inputs
        ]
        if not tasks and request.raw_input.strip():
            tasks = [
                {
                    "title": title[:80],
                    "deadline": None,
                    "deadline_source": None,
                    "type": "general",
                    "priority": "medium",
                    "estimated_minutes": 30,
                    "deadline_mode": "none",
                    "occurrences_per_day": 1,
                }
                for title in re.split(r"\s+và\s+|,|\n", request.raw_input)
                if title.strip()
            ]
        data = {
            "tasks": tasks,
            "goal_analysis": {
                "summary": "Kế hoạch được tạo từ dữ liệu người dùng nhập khi LLM không sẵn sàng.",
                "success_criteria": [],
                "assumptions": ["Ưu tiên được đặt mức trung bình vì chưa có phân tích AI."],
            },
            "risks": [
                {
                    "title": "LLM tạm thời không khả dụng",
                    "severity": "medium",
                    "mitigation": "Có thể bấm cập nhật lại sau khi nhà cung cấp API ổn định.",
                }
            ],
            "focus_sessions": [],
            "review_questions": [],
            "suggested_subtasks": [],
        }
        raw_text = json.dumps({"fallback": True, "error": str(exc), **data}, ensure_ascii=False)
        return StructuredLLMResponse(data=data, raw_text=raw_text, provider="local-fallback")

    @staticmethod
    def _context(request: WorkflowRequest) -> str:
        return json.dumps({
            "task_text": request.raw_input or ", ".join(item.title for item in request.task_inputs),
            "structured_tasks": [item.model_dump(mode="json") for item in request.task_inputs],
            "additional_information": request.planning_notes,
            "calendar_rules": {
                "horizon_days": 14,
                "remaining_time": "fill daytime gaps with personal time and night gaps with rest",
                "conflicts": "higher AI priority wins; move lower priority work to another day",
            },
        }, ensure_ascii=False)

    @staticmethod
    def _validate_task(item: dict) -> Task:
        normalized = dict(item)
        if isinstance(normalized.get("deadline"), str) and "T" in normalized["deadline"]:
            normalized["deadline"] = normalized["deadline"].split("T", maxsplit=1)[0]
        return Task.model_validate(normalized)

    @staticmethod
    def _apply_inputs(tasks: list[Task], inputs: list[TaskInput], additional: str) -> list[Task]:
        if not inputs:
            return tasks
        lookup = {task.title.casefold(): task for task in tasks}
        meal_match = re.search(r"(\d+)\s*bữa", additional.casefold())
        result = []
        for item in inputs:
            title = CalendarWorkflow._input_title(item)
            task = lookup.get(title.casefold()) or Task(title=title, estimated_minutes=item.estimated_minutes)
            task.title = title
            task.estimated_minutes = item.estimated_minutes
            task.deadline_mode = item.deadline_mode
            task.deadline = item.deadline_at.date() if item.deadline_mode == "specific" and item.deadline_at else None
            task.deadline_time = item.deadline_at.time() if item.deadline_mode == "specific" and item.deadline_at else None
            if task.deadline:
                task.deadline_source = "Deadline do người dùng nhập"
            if meal_match and re.search(r"nấu\s*cơm|nau\s*com", item.title.casefold()):
                task.occurrences_per_day = min(int(meal_match.group(1)), 6)
                if task.deadline_mode == "none":
                    task.deadline_mode = "daily"
            result.append(task)
        return result

    @staticmethod
    def _input_title(item: TaskInput) -> str:
        title = item.title.strip()
        if title:
            return title
        if item.deadline_mode == "daily":
            return "Việc hằng ngày"
        if item.deadline_mode == "specific" and item.deadline_at:
            return f"Việc có deadline {item.deadline_at:%d/%m/%Y %H:%M}"
        return "Việc cần sắp lịch"

    @staticmethod
    def _score(task: Task) -> int:
        return {"high": 85, "medium": 60, "low": 30}.get(task.priority, 60) + (10 if task.deadline else 0)

    @staticmethod
    def _reason(task: Task) -> str:
        return "AI đánh giá ưu tiên cao hơn và có deadline" if task.deadline else "AI đánh giá theo tác động mục tiêu"

    @staticmethod
    def _subtasks(tasks: list[Task], suggestions: list[dict]) -> dict[str, list[Subtask]]:
        result = {task.title: [] for task in tasks}
        titles = {task.title.casefold(): task.title for task in tasks}
        for item in suggestions:
            title = titles.get(str(item.get("task_title", "")).casefold())
            if title:
                result[title].append(Subtask.model_validate(item))
        return result

    @classmethod
    def _build_calendar(cls, tasks: list[Task], request: WorkflowRequest) -> tuple[list[ScheduleSession], list[str]]:
        periods = [("morning", 6 * 60, 12 * 60), ("afternoon", 13 * 60, 18 * 60), ("evening", 18 * 60, 22 * 60)]
        today = date.today()
        occupied: dict[date, list[tuple[int, int, Task]]] = {}
        warnings: list[str] = []
        task_blocks: list[ScheduleSession] = []

        if re.search(r"đi\s+làm|đi\s+làm\s+việc|làm\s+việc", request.planning_notes.casefold()):
            for offset in range(14):
                day = today + timedelta(days=offset)
                if day.weekday() < 5:
                    occupied.setdefault(day, []).extend([(8 * 60, 12 * 60, None), (13 * 60, 17 * 60, None)])
                    task_blocks.extend([
                        ScheduleSession(date=day, start_time="08:00", end_time="12:00", task_title="Đi làm", minutes=240, block_type="work", period="morning"),
                        ScheduleSession(date=day, start_time="13:00", end_time="17:00", task_title="Đi làm", minutes=240, block_type="work", period="afternoon"),
                    ])

        def add_task(task: Task, day: date) -> bool:
            max_end = 22 * 60
            if task.deadline and day == task.deadline and task.deadline_time:
                max_end = task.deadline_time.hour * 60 + task.deadline_time.minute
            busy = occupied.setdefault(day, [])
            for period, period_start, period_end in periods:
                end_limit = min(period_end, max_end)
                ordered_busy = sorted(busy, key=lambda item: (item[0], item[1]))
                for start in [period_start] + [
                    end for _, end, _ in ordered_busy if period_start <= end < end_limit
                ]:
                    start = max(start, period_start)
                    conflicts = sorted((s, e) for s, e, _ in busy if s < start + task.estimated_minutes and e > start)
                    next_start = max([start] + [e for s, e in conflicts])
                    if next_start + task.estimated_minutes <= end_limit:
                        busy.append((next_start, next_start + task.estimated_minutes, task))
                        task_blocks.append(ScheduleSession(
                            date=day, start_time=cls._clock(next_start), end_time=cls._clock(next_start + task.estimated_minutes),
                            task_title=task.title, minutes=task.estimated_minutes, block_type="task", period=period,
                        ))
                        return True
            return False

        ordered = sorted(tasks, key=lambda task: (-cls._score(task), task.title))
        for task in ordered:
            days = [today + timedelta(days=index) for index in range(14)]
            occurrences = task.occurrences_per_day if task.deadline_mode == "daily" else 1
            for day in days:
                if task.deadline and day > task.deadline:
                    break
                if task.deadline_mode != "daily" and day != days[0]:
                    continue
                for _ in range(occurrences):
                    if not add_task(task, day):
                        if task.deadline_mode == "daily":
                            warnings.append(f"Không đủ chỗ cho lần lặp hằng ngày của '{task.title}' vào {day}.")
                        else:
                            for later in days[1:]:
                                if not task.deadline or later <= task.deadline:
                                    if add_task(task, later):
                                        break
                            else:
                                warnings.append(f"Xung đột lịch: chưa xếp được '{task.title}'.")
                        break

        return cls._fill_default_blocks_clean(task_blocks), warnings

    @staticmethod
    def _fill_default_blocks(tasks: list[ScheduleSession], occupied: dict[date, list[tuple[int, int, Task]]]) -> list[ScheduleSession]:
        by_day: dict[date, list[ScheduleSession]] = {}
        for item in tasks:
            by_day.setdefault(item.date, []).append(item)
        result = []
        start_day = date.today()
        for offset in range(14):
            day = start_day + timedelta(days=offset)
            items = sorted(by_day.get(day, []), key=lambda item: item.start_time)
            cursor = 0
            for item in items:
                start = CalendarWorkflow._parse_time(item.start_time)
                if cursor < start:
                    result.append(ScheduleSession(date=day, start_time=CalendarWorkflow._clock(cursor), end_time=item.start_time, task_title="Thời gian cá nhân", minutes=start - cursor, block_type="rest" if cursor < 6 * 60 else "personal", period="night" if cursor < 6 * 60 else "morning"))
                result.append(item)
                cursor = CalendarWorkflow._parse_time(item.end_time)
            if cursor < 22 * 60:
                result.append(ScheduleSession(date=day, start_time=CalendarWorkflow._clock(cursor), end_time="22:00", task_title="Thời gian cá nhân", minutes=22 * 60 - cursor, block_type="personal", period="evening"))
            result.append(ScheduleSession(date=day, start_time="22:00", end_time="23:59", task_title="Nghỉ ngơi", minutes=119, block_type="rest", period="night"))
        return sorted(result, key=lambda item: (item.date, item.start_time))

    @staticmethod
    def _fill_default_blocks_clean(tasks: list[ScheduleSession]) -> list[ScheduleSession]:
        by_day: dict[date, list[ScheduleSession]] = {}
        for item in tasks:
            by_day.setdefault(item.date, []).append(item)
        result: list[ScheduleSession] = []
        for offset in range(14):
            day = date.today() + timedelta(days=offset)
            items = sorted(by_day.get(day, []), key=lambda item: item.start_time)
            cursor = 0

            def add_gap(start: int, end: int) -> None:
                CalendarWorkflow._append_gaps(result, day, start, end)
                return
                if start < 6 * 60:
                    rest_end = min(end, 6 * 60)
                    if rest_end - start >= 5:
                        result.append(ScheduleSession(date=day, start_time=CalendarWorkflow._clock(start), end_time=CalendarWorkflow._clock(rest_end), task_title="Nghỉ ngơi", minutes=rest_end - start, block_type="rest", period="night"))
                    start = rest_end
                if end - start >= 5:
                    period = "morning" if start < 12 * 60 else "afternoon" if start < 18 * 60 else "evening"
                    result.append(ScheduleSession(date=day, start_time=CalendarWorkflow._clock(start), end_time=CalendarWorkflow._clock(end), task_title="Thời gian cá nhân", minutes=end - start, block_type="personal", period=period))

            for item in items:
                start = CalendarWorkflow._parse_time(item.start_time)
                if cursor < start:
                    add_gap(cursor, start)
                result.append(item)
                cursor = CalendarWorkflow._parse_time(item.end_time)
            if cursor < 22 * 60:
                add_gap(cursor, 22 * 60)
            result.append(ScheduleSession(date=day, start_time="22:00", end_time="23:59", task_title="Nghỉ ngơi", minutes=119, block_type="rest", period="night"))
        return sorted(result, key=lambda item: (item.date, item.start_time))

    @staticmethod
    def _append_gaps(result: list[ScheduleSession], day: date, start: int, end: int) -> None:
        while start < end:
            if start < 6 * 60:
                chunk_end = min(end, 6 * 60)
                block_type, title, period = "rest", "Nghỉ ngơi", "night"
            else:
                chunk_end = min(end, 12 * 60 if start < 12 * 60 else 18 * 60 if start < 18 * 60 else 22 * 60)
                block_type, title = "personal", "Thời gian cá nhân"
                period = "morning" if start < 12 * 60 else "afternoon" if start < 18 * 60 else "evening"
            if chunk_end - start >= 5:
                result.append(ScheduleSession(date=day, start_time=CalendarWorkflow._clock(start), end_time=CalendarWorkflow._clock(chunk_end), task_title=title, minutes=chunk_end - start, block_type=block_type, period=period))
            start = chunk_end

    @staticmethod
    def _parse_time(value: str) -> int:
        hours, minutes = value.split(":")
        return int(hours) * 60 + int(minutes)

    @staticmethod
    def _clock(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Task(BaseModel):
    title: str = Field(min_length=1)
    deadline_mode: Literal["daily", "specific", "none"] = "none"
    deadline: date | None = None
    deadline_time: time | None = None
    deadline_source: str | None = None
    type: str = "general"
    priority: Literal["low", "medium", "high"] = "medium"
    estimated_minutes: int = Field(default=30, ge=5, le=480)
    occurrences_per_day: int = Field(default=1, ge=1, le=6)


class Subtask(BaseModel):
    title: str
    estimated_minutes: int = Field(ge=5, le=480)
    definition_of_done: str


class ScheduleSession(BaseModel):
    date: date
    start_time: str
    end_time: str
    task_title: str
    minutes: int = Field(ge=5, le=480)
    block_type: Literal["task", "personal", "rest", "work"] = "task"
    period: Literal["morning", "afternoon", "evening", "night"] = "evening"


class GoalAnalysis(BaseModel):
    summary: str = ""
    success_criteria: list[str] = []
    assumptions: list[str] = []


class Risk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"] = "medium"
    mitigation: str


class FocusSession(BaseModel):
    task_title: str
    objective: str
    method: str
    checklist: list[str] = []


class ReviewQuestion(BaseModel):
    question: str
    purpose: str


class TaskInput(BaseModel):
    title: str = ""
    deadline_mode: Literal["daily", "specific", "none"] = "none"
    deadline_at: datetime | None = None
    type: str = "general"
    priority: Literal["low", "medium", "high"] = "medium"
    estimated_minutes: int = Field(default=30, ge=5, le=480)

    @model_validator(mode="after")
    def validate_deadline(self):
        if self.deadline_mode == "specific" and self.deadline_at is None:
            raise ValueError("Deadline cụ thể phải có ngày và giờ.")
        return self


class WorkflowRequest(BaseModel):
    user_id: str = Field(min_length=1)
    display_name: str = ""
    raw_input: str = ""
    task_inputs: list[TaskInput] = Field(default_factory=list)
    available_minutes_per_day: int = Field(default=120, ge=15, le=1440)
    deadline_at: datetime | None = None
    daily_start_time: time = time(hour=19)
    daily_end_time: time = time(hour=21)
    preferred_weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1)
    energy_peak: Literal["morning", "afternoon", "evening", "flexible"] = "flexible"
    work_style: Literal["deep_focus", "short_sprints", "flexible"] = "flexible"
    focus_minutes: int = Field(default=25, ge=15, le=120)
    existing_commitments: str = Field(default="", max_length=1000)
    planning_notes: str = Field(default="", max_length=1000)
    horizon_days: int = Field(default=14, ge=14, le=14)

    @model_validator(mode="before")
    @classmethod
    def allow_planning_notes_only(cls, data):
        if not isinstance(data, dict):
            return data
        has_tasks = bool(data.get("task_inputs"))
        raw_input = str(data.get("raw_input") or "").strip()
        planning_notes = str(data.get("planning_notes") or "").strip()
        if not has_tasks and len(raw_input) < 3 and len(planning_notes) >= 3:
            data = {**data, "raw_input": planning_notes}
        return data

    @model_validator(mode="after")
    def validate_input(self):
        if not self.task_inputs and len(self.raw_input.strip()) < 3:
            raise ValueError("Cần thêm ít nhất một công việc hoặc mô tả mục tiêu.")
        return self


class WorkflowResult(BaseModel):
    plan_id: str | None = None
    created_at: datetime | None = None
    plan_input: WorkflowRequest | None = None
    llm_provider: str
    llm_model: str
    llm_raw_preview: str = ""
    tasks: list[Task]
    priorities: list[dict]
    subtasks: dict[str, list[Subtask]]
    schedule: list[ScheduleSession]
    goal_analysis: GoalAnalysis = Field(default_factory=GoalAnalysis)
    schedule_reasoning: str = ""
    risks: list[Risk] = []
    focus_sessions: list[FocusSession] = []
    review_questions: list[ReviewQuestion] = []
    warnings: list[str] = []
    needs_confirmation: bool = False
    confidence: float = Field(ge=0, le=1)


class PlanSummary(BaseModel):
    plan_id: str
    created_at: datetime
    title: str
    task_count: int


class GmailScanRequest(BaseModel):
    user_id: str = Field(min_length=1)
    display_name: str = ""
    days: int = Field(default=3, ge=1, le=30)
    max_results: int = Field(default=50, ge=1, le=200)

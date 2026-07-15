import re

from app.schemas import Task


def validate_grounding(tasks: list[Task], raw_input: str) -> list[str]:
    warnings = []
    for task in tasks:
        if task.deadline and not re.search(rf"\b{task.deadline.isoformat()}\b", raw_input):
            warnings.append(f"Deadline của '{task.title}' không có bằng chứng trực tiếp; đã loại bỏ.")
            task.deadline = None
            task.deadline_source = None
    return warnings


def validate_schedule(total_minutes: int, daily_limit: int) -> list[str]:
    return ["Kế hoạch vượt thời gian rảnh trong ngày; cần xác nhận hoặc replan."] if total_minutes > daily_limit else []


def confidence(warnings: list[str], task_count: int) -> float:
    if not task_count:
        return 0.0
    return max(0.0, min(1.0, 0.95 - (0.12 * len(warnings))))

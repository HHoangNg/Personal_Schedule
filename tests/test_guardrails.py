from datetime import date

from app.reliability.guardrails import validate_grounding, validate_schedule
from app.schemas import Task


def test_deadline_without_explicit_evidence_is_removed():
    task = Task(title="report", deadline=date(2026, 7, 20))
    warnings = validate_grounding([task], "Tôi cần làm report trong tuần này")
    assert task.deadline is None
    assert warnings


def test_explicit_iso_deadline_is_kept():
    task = Task(title="report", deadline=date(2026, 7, 20))
    assert validate_grounding([task], "Deadline report là 2026-07-20") == []
    assert task.deadline == date(2026, 7, 20)


def test_overload_is_reported():
    assert validate_schedule(121, 120)
    assert validate_schedule(120, 120) == []

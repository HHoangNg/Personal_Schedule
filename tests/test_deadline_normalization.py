from app.workflow.personalized_service import PersonalizedProductivityWorkflow


def test_llm_datetime_deadline_is_normalized_before_task_validation():
    task = PersonalizedProductivityWorkflow._validate_task(
        {
            "title": "Học tiếng Anh",
            "deadline": "2026-07-15T09:35:00",
            "deadline_source": "deadline_at",
            "type": "learning",
            "priority": "high",
            "estimated_minutes": 35,
        }
    )

    assert task.deadline.isoformat() == "2026-07-15"

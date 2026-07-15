from app.core.settings import Settings
from app.integrations.gmail import GmailMessage, GmailScheduleImporter


class FakeGmailClient:
    def scan_recent(self, days: int = 3, max_results: int = 50):
        return [
            GmailMessage(
                message_id="m1",
                sender="teacher@example.com",
                subject="Lịch học tiếng Anh tối thứ 5",
                date="Wed, 15 Jul 2026 08:00:00 +0700",
                snippet="Lớp học diễn ra lúc 19:00.",
            ),
            GmailMessage(
                message_id="m2",
                sender="promo@example.com",
                subject="Khuyến mãi cuối tuần",
                date="Wed, 15 Jul 2026 09:00:00 +0700",
                snippet="Mua hàng giảm giá.",
            ),
        ]


def test_gmail_importer_builds_calendar_request_from_relevant_messages():
    importer = GmailScheduleImporter(Settings(llm_provider="mock"), client=FakeGmailClient())

    request = importer.build_request(
        user_id="gmail-user",
        display_name="Minh",
        days=3,
        max_results=50,
    )

    assert request.user_id == "gmail-user"
    assert request.display_name == "Minh"
    assert "Gmail 3" in request.planning_notes
    assert "Lịch học tiếng Anh" in request.raw_input
    assert "Khuyến mãi" not in request.raw_input

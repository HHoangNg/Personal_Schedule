import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.providers import build_provider
from app.schemas import WorkflowRequest


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SCHEDULE_KEYWORDS = (
    "calendar",
    "class",
    "deadline",
    "due",
    "event",
    "flight",
    "hạn",
    "hẹn",
    "họp",
    "interview",
    "lịch",
    "meeting",
    "reservation",
    "schedule",
    "thi",
    "workshop",
)

GMAIL_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "relevant_notes": {"type": "array", "items": {"type": "string"}},
        "ignored_message_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "relevant_notes", "ignored_message_ids"],
}


@dataclass
class GmailMessage:
    message_id: str
    sender: str
    subject: str
    date: str
    snippet: str


class GmailClient:
    """Reads recent Gmail metadata/snippets with a read-only OAuth token."""

    def __init__(self, credentials_path: str, token_path: str):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)

    def scan_recent(self, days: int = 3, max_results: int = 50) -> list[GmailMessage]:
        service = self._service()
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=f"newer_than:{days}d",
                maxResults=max_results,
            )
            .execute()
        )
        messages = response.get("messages", [])
        return [self._get_message(service, item["id"]) for item in messages]

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), GMAIL_SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Không tìm thấy Gmail credentials tại {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), GMAIL_SCOPES
                )
                credentials = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=credentials)

    @staticmethod
    def _get_message(service, message_id: str) -> GmailMessage:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {
            item["name"].casefold(): item.get("value", "")
            for item in message.get("payload", {}).get("headers", [])
        }
        return GmailMessage(
            message_id=message_id,
            sender=headers.get("from", ""),
            subject=headers.get("subject", ""),
            date=headers.get("date", ""),
            snippet=message.get("snippet", ""),
        )


class GmailScheduleImporter:
    """Turns recent Gmail messages into planning notes for the calendar workflow."""

    def __init__(self, settings, client: GmailClient | None = None):
        self.settings = settings
        self.client = client or GmailClient(settings.gmail_credentials_path, settings.gmail_token_path)
        self.provider = build_provider(settings)

    def build_request(self, user_id: str, display_name: str, days: int, max_results: int) -> WorkflowRequest:
        messages = self.client.scan_recent(days=days, max_results=max_results)
        notes, warnings = self._extract_schedule_notes(messages, days)
        if not notes:
            notes = [f"Không tìm thấy email liên quan lịch trình trong {days} ngày gần nhất."]
        planning_notes = "\n".join(
            [
                f"Nguồn: Gmail {days} ngày gần nhất.",
                *notes,
                *warnings,
            ]
        )
        return WorkflowRequest(
            user_id=user_id,
            display_name=display_name,
            raw_input="\n".join(notes),
            planning_notes=planning_notes,
            horizon_days=14,
        )

    def _extract_schedule_notes(
        self, messages: list[GmailMessage], days: int
    ) -> tuple[list[str], list[str]]:
        if not messages:
            return [], [f"Gmail không có email nào trong {days} ngày gần nhất."]
        prompt = json.dumps(
            {
                "instruction": (
                    "Lọc các email liên quan lịch trình, deadline, cuộc hẹn, lớp học, "
                    "sự kiện, chuyến đi hoặc việc cần đưa vào lịch. Trả JSON theo schema."
                ),
                "messages": [message.__dict__ for message in messages],
            },
            ensure_ascii=False,
        )
        try:
            response = self.provider.generate_json(prompt, GMAIL_ANALYSIS_SCHEMA)
            notes = [
                str(item).strip()
                for item in response.data.get("relevant_notes", [])
                if str(item).strip()
            ]
            if notes:
                return notes, []
        except Exception as exc:
            return self._local_filter(messages), [
                f"LLM không phân tích được Gmail nên dùng bộ lọc cục bộ: {type(exc).__name__}: {exc}"
            ]
        return self._local_filter(messages), ["LLM không tìm thấy email lịch trình rõ ràng."]

    @staticmethod
    def _local_filter(messages: list[GmailMessage]) -> list[str]:
        pattern = re.compile("|".join(re.escape(keyword) for keyword in SCHEDULE_KEYWORDS), re.I)
        notes = []
        for message in messages:
            haystack = f"{message.subject}\n{message.snippet}"
            if pattern.search(haystack):
                notes.append(
                    "Email Gmail liên quan lịch trình: "
                    f"{message.subject} | từ {message.sender} | ngày {message.date} | {message.snippet}"
                )
        return notes

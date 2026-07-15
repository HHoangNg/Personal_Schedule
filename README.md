# AI Personal Productivity OS

Ứng dụng lập lịch cá nhân bằng AI. Người dùng nhập công việc, deadline, ghi chú riêng hoặc quét Gmail; hệ thống dùng GPT/Gemini để phân tích, xếp lịch 14 ngày, lưu lại lịch và đồng bộ memory lên Qdrant.

## Tính năng chính

- Giao diện tiếng Việt để tạo/chỉnh sửa lịch theo `user_id`.
- Thêm công việc bằng từng ô riêng, có deadline hằng ngày hoặc thời gian cụ thể.
- Nhập “Thông tin thêm” để cập nhật lịch mà không cần thêm task thủ công.
- Quét Gmail 3 ngày gần nhất, lọc email liên quan lịch trình rồi đưa vào lịch.
- Chọn LLM: OpenAI, Gemini hoặc chế độ đối chiếu cả hai.
- Lưu dữ liệu vào SQLite, file JSON và Qdrant Cloud/local.
- Có Docker, CI GitHub Actions, test và eval golden set.

## Stack

- Backend: FastAPI, Pydantic
- LLM: OpenAI API, Gemini API
- Memory/vector DB: Qdrant + Voyage embeddings
- Gmail: Google OAuth read-only
- Frontend: HTML/CSS/JS thuần
- Test/CI: pytest, ruff, GitHub Actions

## Cài đặt nhanh

```powershell
python -m venv .personal_schedule
.\.personal_schedule\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy .env.example .env
```

Điền các key cần dùng trong `.env`:

```env
LLM_PROVIDER=gemini
OPENAI_API_KEY=
GEMINI_API_KEY=

QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=personal_productivity_memory
QDRANT_VECTOR_SIZE=1024
QDRANT_VECTOR_NAME=dense

VOYAGE_API_KEY=
VOYAGE_MODEL=voyage-3.5
```

Chạy app:

```powershell
.\.personal_schedule\Scripts\python.exe -m uvicorn app.main:app --reload
```

Mở:

```text
http://localhost:8000/
```

## Chọn LLM

```env
LLM_PROVIDER=openai
LLM_PROVIDER=gemini
LLM_PROVIDER=compare
```

`compare` sẽ gọi cả GPT và Gemini để đối chiếu, sau đó dùng kết quả chính để lập lịch.

## Gmail

Để quét Gmail:

1. Bật Gmail API trong Google Cloud Console.
2. Tạo OAuth Client loại Desktop app.
3. Lưu credentials tại:

```text
secrets/gmail_credentials.json
```

`.env`:

```env
GMAIL_CREDENTIALS_PATH=secrets/gmail_credentials.json
GMAIL_TOKEN_PATH=data/gmail_token.json
```

Lần đầu bấm “Quét Gmail và cập nhật lịch”, trình duyệt sẽ mở OAuth để chọn tài khoản Gmail.

## Docker

Không bắt buộc phải build Docker trước khi push GitHub. Chỉ cần commit `Dockerfile`, `docker-compose.yml` và CI sẽ build sau khi push.

Chạy Docker local:

```powershell
docker compose up --build
```

Build image thủ công:

```powershell
docker build -t personal-schedule-ai .
docker run --env-file .env -p 8000:8000 personal-schedule-ai
```

## Kiểm tra

```powershell
ruff check .
python -m pytest
python -m evals.run --dataset evals/data/golden.jsonl
```

## CI/CD

GitHub Actions nằm ở:

```text
.github/workflows/ci.yml
```

CI sẽ chạy:

- `ruff check`
- `pytest`
- golden-set eval
- build/push Docker image lên GHCR khi push vào `main`

## File nên commit

```text
app/
tests/
evals/
.github/workflows/ci.yml
Dockerfile
docker-compose.yml
requirements.txt
pyproject.toml
README.md
README_FULL.md
.env.example
.dockerignore
.gitignore
ai_personal_productivity_os_workflow.md
```

Không commit:

```text
.env
data/
secrets/
.personal_schedule/
.venv/
*.egg-info/
__pycache__/
.pytest_cache/
.ruff_cache/
```

## Tài liệu chi tiết

Xem [README_FULL.md](README_FULL.md) nếu cần hướng dẫn đầy đủ về Qdrant, Gmail, hallucination handling, evaluation và roadmap.

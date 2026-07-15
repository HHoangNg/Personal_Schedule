from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

app = FastAPI(title="AI Personal Productivity OS", version="0.1.0")
app.include_router(router)

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(WEB_DIR / "calendar.html")


@app.get("/health")
def health():
    return {"status": "ok"}

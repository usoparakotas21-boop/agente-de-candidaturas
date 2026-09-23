from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import json

from .auth import AuthMiddleware, authenticated_user, router as auth_router
from .gmail_integration import router as gmail_router
from .gmail_monitor import router as gmail_monitor_router, start_monitor, stop_monitor
from .queue_routes import router as queue_router
from .database import SessionLocal, engine, Base
from .models import Candidate, Job, Application
from .resume_importer import parse_resume

app = FastAPI(title="Agente de Candidaturas", version="0.23.0")
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(gmail_router)
app.include_router(gmail_monitor_router)
app.include_router(queue_router)

DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"

@app.get("/")
def root():
    return {"status": "online", "version": "0.23.0"}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    if not DASHBOARD_PATH.is_file():
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    start_monitor()

@app.on_event("shutdown")
async def shutdown():
    await stop_monitor()
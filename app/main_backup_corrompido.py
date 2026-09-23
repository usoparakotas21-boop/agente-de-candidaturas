import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select, text
from starlette.concurrency import run_in_threadpool

from . import models  # noqa: F401
from .auth import (
    AuthMiddleware,
    authenticated_user,
    router as auth_router,
)
from .gmail_integration import router as gmail_router
from .gmail_monitor import (
from .queue_routes import router as queue_router
    router as gmail_monitor_router,
from .queue_routes import router as queue_router
    start_monitor as start_gmail_monitor,
    stop_monitor as stop_gmail_monitor,
)
from .analyzer import analyze_job
from .cover_letter import (
    generate_cover_letter,
    generate_cover_letter_docx,
)
from .decision_engine import (
    decide_opportunity,
    normalize_preferences,
)
from .database import Base, SessionLocal, engine
from .job_intake import parse_job_text
from .job_quality import assess_job_capture
from .job_source_fetcher import (
    SourceFetchError,
    fetch_job_posting,
    infer_from_public_url,
)
from .job_file_intake import (
    MAX_JOB_FILE_BYTES,
    OCRUnavailableError,
    extract_job_file_text,
)
from .models import (
    Application,
    ApplicationEvent,
    Candidate,
    Experience,
    Job,
    Skill,
)
from .resume_importer import MAX_UPLOAD_BYTES, parse_resume
from .resume_document import MASTER_PROFILE, generate_docx
from .resume_generator import generate_resume
from .resume_personalizer import personalize_resume


app = FastAPI(
    title="Agente de Candidaturas - Paulo Henrique",
    version="0.21.0",
)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(gmail_router)
app.include_router(gmail_monitor_router)


APPLICATION_STATUSES = (
    "IDENTIFICADA",
    "ANALISADA",
    "PERSONALIZADA",
    "CURRICULO_GERADO",
    "CANDIDATURA_ENVIADA",
    "ENTREVISTA",
    "APROVADO",
    "RECUSADO",
    "ARQUIVADA",
)

DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"


def _owner_id(user: Any) -> str | None:
    # FastAPI resolves Depends before an HTTP route is executed.  The unit
    # tests also call route functions directly, in which case the default
    # Depends object is still present and represents the legacy single-user
    # test fixture (rows without owner_id).
    if not isinstance(user, dict):
        return None
    return user.get("id")


def _candidate_for_user(db, user: dict[str, Any]) -> Candidate | None:
    query = select(Candidate).order_by(Candidate.id)
    owner_id = _owner_id(user)
    if owner_id is not None:
        query = query.where(Candidate.owner_id == owner_id)
    candidate = db.scalar(query)
    if owner_id is not None and candidate is None:
        raise HTTPException(
            status_code=409,
            detail="Perfil do candidato ainda nao configurado.",
        )
    return candidate


def _job_for_user(db, job_id: int, user: dict[str, Any]) -> Job | None:
    query = select(Job).where(Job.id == job_id)
    owner_id = _owner_id(user)
    if owner_id is not None:
        query = query.where(Job.owner_id == owner_id)
    return db.scalar(query)


def _application_for_user(
    db,
    application_id: int,
    user: dict[str, Any],
) -> Application | None:
    query = (
        select(Application)
        .join(Application.job)
        .where(Application.id == application_id)
    )
    owner_id = _owner_id(user)
    if owner_id is not None:
        query = query.where(Job.owner_id == owner_id)
    return db.scalar(query)


class JobRequest(BaseModel):
    title: str
    description: str


class JobCreateRequest(BaseModel):
    source: str = "manual"
    external_id: str
    company: str
    title: str
    location: str = ""
    modality: str = ""
    salary: str = ""
    url: str = ""
    description: str


class JobIntakeRequest(BaseModel):
    raw_text: str
    source: str = "texto"
    auto_analyze: bool = True
    reprocess_existing: bool = False


class JobIntakeConfirmRequest(BaseModel):
    external_id: str
    source: str = "print"
    company: str
    title: str
    location: str = ""
    modality: str = ""
    salary: str = ""
    url: str = ""
    description: str
    auto_analyze: bool = True


class ResumeRequest(BaseModel):
    title: str
    resume: dict


class ApplicationStatusRequest(BaseModel):
    status: Literal[
        "IDENTIFICADA",
        "ANALISADA",
        "PERSONALIZADA",
        "CURRICULO_GERADO",
        "CANDIDATURA_ENVIADA",
        "ENTREVISTA",
        "APROVADO",
        "RECUSADO",
        "ARQUIVADA",
    ]
    note: str = ""


class CandidatePreferencesRequest(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    minimum_score: int = 65
    automatic_score: int = 85
    allow_automatic: bool = False
    max_daily_applications: int = 5


def _split_target_roles(target_roles: str) -> list[str]:
    return [item.strip() for item in target_roles.split(",") if item.strip()]


def _fallback_profile() -> dict[str, Any]:
    experiences = [
        {
            "company": experience["company"],
            "role": experience["role"],
            "description": " ".join(experience["bullets"]),
        }
        for experience in MASTER_PROFILE["experiences"]
    ]

    return {
        "name": MASTER_PROFILE["name"],
        "summary": MASTER_PROFILE["summary"],
        "target_roles": [
            "Analista de RH",
            "Analista de DP",
            "Supervisor de RH",
            "Supervisor de DP",
            "Coordenador de RH",
            "Coordenador de DP",
            "Gerente de RH",
            "Gerente de DP",
        ],
        "experience_texts": [item["description"] for item in experiences],
        "experiences": experiences,
        "skills": list(MASTER_PROFILE["skills"]),
        "location": MASTER_PROFILE["location"],
        "contact": {
            "phone": MASTER_PROFILE["phone"],
            "email": MASTER_PROFILE["email"],
            "linkedin": MASTER_PROFILE["linkedin"],
            "location": MASTER_PROFILE["location"],
        },
    }


def _candidate_profile(candidate: Candidate | None) -> dict[str, Any]:
    if candidate is None:
        return _fallback_profile()

    profile_data: dict[str, Any] = {}
    if candidate.profile_data:
        try:
            profile_data = json.loads(candidate.profile_data)
        except json.JSONDecodeError:
            profile_data = {}

    experiences = [
        {
            "company": experience.company,
            "role": experience.role,
            "description": experience.description,
            "start_date": experience.start_date,
            "end_date": experience.end_date,
            "period": " - ".join(
                value
                for value in (experience.start_date, experience.end_date)
                if value
            ),
            "bullets": [
                line.strip()
                for line in experience.description.splitlines()
                if line.strip()
            ],
        }
        for experience in candidate.experiences
    ]

    return {
        "name": candidate.name,
        "summary": candidate.summary,
        "target_roles": _split_target_roles(candidate.target_roles),
        "experience_texts": [item["description"] for item in experiences],
        "experiences": experiences,
        "skills": [skill.name for skill in candidate.skills],
        "headline": profile_data.get("headline", ""),
        "education": profile_data.get("education", []),
        "languages": profile_data.get("languages", []),
        "location": candidate.location,
        "contact": {
            "phone": candidate.phone,
            "email": candidate.email,
            "linkedin": candidate.linkedin,
            "location": candidate.location,
        },
    }


def _job_text(job: Job) -> str:
    return "\n".join(
        [
            job.title or "",
            job.company or "",
            job.location or "",
            job.modality or "",
            job.salary or "",
            job.description or "",
        ]
    )


def _build_application(job: Job, candidate: Candidate | None) -> dict[str, Any]:
    profile = _candidate_profile(candidate)
    analysis = analyze_job(_job_text(job), profile)
    personalization = personalize_resume(job.title, job.description, profile)

    resume_candidate = {
        "name": profile["name"],
        "contact": profile["contact"],
        "target": job.title,
        "headline": profile.get("headline", ""),
        "skills": profile.get("skills", []),
        "education": profile.get("education", []),
        "languages": profile.get("languages", []),
    }
    resume = generate_resume(resume_candidate, personalization)
    resume["target"] = job.title

    return {
        "profile": profile,
        "analysis": analysis,
        "personalization": personalization,
        "resume": resume,
    }


def _add_application_event(
    db,
    application: Application,
    status: str,
    note: str = "",
) -> None:
    application.status = status
    db.add(
        ApplicationEvent(
            application_id=application.id,
            status=status,
            note=note or None,
        )
    )


def _ensure_application(
    db,
    job: Job,
    candidate: Candidate | None,
) -> Application:
    application = db.scalar(
        select(Application).where(Application.job_id == job.id)
    )
    if application is not None:
        return application

    application = Application(
        job_id=job.id,
        candidate_id=candidate.id if candidate else None,
        status="IDENTIFICADA",
    )
    db.add(application)
    db.flush()
    _add_application_event(
        db,
        application,
        "IDENTIFICADA",
        "Vaga adicionada ao histÃ³rico.",
    )
    return application


def _advance_application(
    db,
    application: Application,
    status: str,
    note: str = "",
) -> None:
    current_index = APPLICATION_STATUSES.index(application.status)
    target_index = APPLICATION_STATUSES.index(status)
    if target_index > current_index:
        _add_application_event(db, application, status, note)


def _serialize_application(application: Application) -> dict[str, Any]:
    analysis = None
    if application.analysis_data:
        try:
            analysis = json.loads(application.analysis_data)
        except json.JSONDecodeError:
            analysis = None

    try:
        decision_reasons = json.loads(application.decision_reasons or "[]")
    except json.JSONDecodeError:
        decision_reasons = []
    try:
        field_confidence = json.loads(application.field_confidence or "{}")
    except json.JSONDecodeError:
        field_confidence = {}

    return {
        "id": application.id,
        "job_id": application.job_id,
        "candidate_id": application.candidate_id,
        "company": application.job.company,
        "job_title": application.job.title,
        "status": application.status,
        "analysis_score": application.analysis_score,
        "personalization_score": application.personalization_score,
        "recommendation": application.recommendation,
        "queue_decision": application.queue_decision or "REVISAR",
        "decision_reasons": decision_reasons,
        "capture_confidence": application.capture_confidence,
        "field_confidence": field_confidence,
        "analysis": analysis,
        "document_path": application.document_path,
        "cover_letter_text": application.cover_letter_text,
        "cover_letter_path": application.cover_letter_path,
        "created_at": application.created_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
        "events": [
            {
                "id": event.id,
                "status": event.status,
                "note": event.note,
                "created_at": event.created_at.isoformat(),
            }
            for event in application.events
        ],
    }


def _candidate_preferences(candidate: Candidate | None) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    if candidate is not None and candidate.preferences_data:
        try:
            value = json.loads(candidate.preferences_data)
            if isinstance(value, dict):
                stored = value
        except json.JSONDecodeError:
            stored = {}
    return normalize_preferences(
        stored,
        target_roles=candidate.target_roles if candidate is not None else "",
        location=candidate.location if candidate is not None else "",
    )


def _apply_queue_decision(
    application: Application,
    candidate: Candidate | None,
    analysis: dict[str, Any] | None,
) -> None:
    result = decide_opportunity(
        {
            "title": application.job.title,
            "company": application.job.company,
            "location": application.job.location,
            "modality": application.job.modality,
            "description": application.job.description,
        },
        analysis,
        _candidate_preferences(candidate),
        capture_confidence=application.capture_confidence,
    )
    application.queue_decision = result["decision"]
    application.decision_reasons = json.dumps(
        result["reasons"],
        ensure_ascii=False,
    )


def _save_capture_quality(
    application: Application,
    quality: dict[str, Any],
) -> None:
    application.capture_confidence = int(quality["confidence"])
    application.field_confidence = json.dumps(
        quality["field_confidence"],
        ensure_ascii=False,
    )


def _save_analysis(
    application: Application,
    analysis: dict[str, Any],
    candidate: Candidate | None,
) -> None:
    application.analysis_score = analysis["score"]
    application.recommendation = analysis["recommendation"]
    application.analysis_data = json.dumps(
        analysis,
        ensure_ascii=False,
    )
    _apply_queue_decision(application, candidate, analysis)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        application_columns = {
            column["name"]
            for column in inspect(engine).get_columns("applications")
        }
        candidate_columns = {
            column["name"]
            for column in inspect(engine).get_columns("candidates")
        }
        job_columns = {
            column["name"]
            for column in inspect(engine).get_columns("jobs")
        }

        if "owner_id" not in candidate_columns:
            db.execute(
                text("ALTER TABLE candidates ADD COLUMN owner_id VARCHAR(36)")
            )
        if "profile_data" not in candidate_columns:
            db.execute(
                text("ALTER TABLE candidates ADD COLUMN profile_data TEXT")
            )
        if "resume_filename" not in candidate_columns:
            db.execute(
                text(
                    "ALTER TABLE candidates "
                    "ADD COLUMN resume_filename VARCHAR(300)"
                )
            )
        if "preferences_data" not in candidate_columns:
            db.execute(
                text("ALTER TABLE candidates ADD COLUMN preferences_data TEXT")
            )
        if "owner_id" not in job_columns:
            db.execute(
                text("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36)")
            )
        if "cover_letter_text" not in application_columns:
            db.execute(
                text("ALTER TABLE applications ADD COLUMN cover_letter_text TEXT")
            )
        if "cover_letter_path" not in application_columns:
            db.execute(
                text("ALTER TABLE applications ADD COLUMN cover_letter_path TEXT")
            )
        if "analysis_data" not in application_columns:
            db.execute(
                text("ALTER TABLE applications ADD COLUMN analysis_data TEXT")
            )
        if "queue_decision" not in application_columns:
            db.execute(
                text(
                    "ALTER TABLE applications ADD COLUMN queue_decision "
                    "VARCHAR(20) DEFAULT 'REVISAR' NOT NULL"
                )
            )
        if "decision_reasons" not in application_columns:
            db.execute(
                text("ALTER TABLE applications ADD COLUMN decision_reasons TEXT")
            )
        if "capture_confidence" not in application_columns:
            db.execute(
                text(
                    "ALTER TABLE applications ADD COLUMN capture_confidence INTEGER"
                )
            )
        if "field_confidence" not in application_columns:
            db.execute(
                text("ALTER TABLE applications ADD COLUMN field_confidence TEXT")
            )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_applications_status "
                "ON applications (status)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_applications_updated_at "
                "ON applications (updated_at)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_applications_queue_decision "
                "ON applications (queue_decision)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_candidates_owner_id "
                "ON candidates (owner_id)"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_jobs_owner_id "
                "ON jobs (owner_id)"
            )
        )
        jobs = db.scalars(select(Job)).all()
        for job in jobs:
            candidate = db.scalar(
                select(Candidate)
                .where(Candidate.owner_id == job.owner_id)
                .order_by(Candidate.id)
            )
            _ensure_application(db, job, candidate)
        if engine.dialect.name == "sqlite":
            db.execute(text("PRAGMA optimize"))
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
async def startup_gmail_monitor():
    start_gmail_monitor()


@app.on_event("shutdown")
async def shutdown_gmail_monitor():
    await stop_gmail_monitor()


@app.get("/")
def root():
    return {
        "agente": "Agente de Candidaturas",
        "candidato": "Paulo Henrique Santos Oliveira",
        "status": "online",
        "version": "0.21.0",
        "dashboard": "/dashboard",
    }


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    if not DASHBOARD_PATH.is_file():
        raise HTTPException(status_code=500, detail="Dashboard nÃ£o encontrado.")
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/profile")
def get_profile(
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()
    try:
        query = select(Candidate).order_by(Candidate.id)
        owner_id = _owner_id(user)
        if owner_id is not None:
            query = query.where(Candidate.owner_id == owner_id)
        candidate = db.scalar(query)
        if candidate is None:
            return {"configured": False}
        return {
            "configured": True,
            "name": candidate.name,
            "location": candidate.location,
            "email": candidate.email,
            "target_roles": _split_target_roles(candidate.target_roles),
            "resume_filename": candidate.resume_filename,
            "experiences": len(candidate.experiences),
            "skills": len(candidate.skills),
        }
    finally:
        db.close()


@app.get("/preferences")
def get_preferences(
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()
    try:
        candidate = _candidate_for_user(db, user)
        if candidate is None:
            raise HTTPException(status_code=409, detail="Importe o curriculo primeiro.")
        return _candidate_preferences(candidate)
    finally:
        db.close()


@app.put("/preferences")
def update_preferences(
    request: CandidatePreferencesRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()
    try:
        candidate = _candidate_for_user(db, user)
        if candidate is None:
            raise HTTPException(status_code=409, detail="Importe o curriculo primeiro.")
        preferences = normalize_preferences(request.model_dump())
        candidate.preferences_data = json.dumps(preferences, ensure_ascii=False)

        query = select(Application).join(Application.job)
        owner_id = _owner_id(user)
        if owner_id is not None:
            query = query.where(Job.owner_id == owner_id)
        applications = db.scalars(query).all()
        changed = 0
        for application in applications:
            previous = application.queue_decision
            analysis = None
            if application.analysis_data:
                try:
                    analysis = json.loads(application.analysis_data)
                except json.JSONDecodeError:
                    analysis = None
            _apply_queue_decision(application, candidate, analysis)
            if previous != application.queue_decision:
                changed += 1
                db.add(
                    ApplicationEvent(
                        application=application,
                        status=application.status,
                        note=(
                            "Decisao da fila recalculada: "
                            f"{application.queue_decision}."
                        ),
                    )
                )
        db.commit()
        return {
            "status": "PREFERENCIAS_ATUALIZADAS",
            "preferences": preferences,
            "decisions_updated": changed,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/profile/resume")
async def upload_profile_resume(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(authenticated_user),
):
    filename = Path(
        (file.filename or "curriculo.docx").replace("\\", "/")
    ).name
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()

    try:
        parsed = parse_resume(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    owner_id = _owner_id(user)
    if owner_id is None:
        raise HTTPException(
            status_code=409,
            detail="Importacao disponivel somente no modo autenticado.",
        )

    db = SessionLocal()
    try:
        candidate = db.scalar(
            select(Candidate).where(Candidate.owner_id == owner_id)
        )
        if candidate is None:
            candidate = Candidate(
                owner_id=owner_id,
                name=parsed["name"],
                location=parsed["location"],
                email=parsed["email"],
                phone=parsed["phone"],
                linkedin=parsed["linkedin"],
                target_roles=parsed["target_roles"],
                summary=parsed["summary"],
            )
            db.add(candidate)
            db.flush()
        else:
            candidate.name = parsed["name"]
            candidate.location = parsed["location"]
            candidate.email = parsed["email"]
            candidate.phone = parsed["phone"]
            candidate.linkedin = parsed["linkedin"]
            candidate.target_roles = parsed["target_roles"]
            candidate.summary = parsed["summary"]
            candidate.experiences.clear()
            candidate.skills.clear()

        candidate.profile_data = json.dumps(
            {
                "headline": parsed["headline"],
                "education": parsed["education"],
                "languages": parsed["languages"],
            },
            ensure_ascii=False,
        )
        candidate.resume_filename = parsed["source_filename"]

        for item in parsed["experiences"]:
            candidate.experiences.append(
                Experience(
                    company=item["company"],
                    role=item["role"],
                    start_date=item["start_date"],
                    end_date=item["end_date"],
                    description=item["description"],
                )
            )
        for skill_name in parsed["skills"]:
            candidate.skills.append(
                Skill(
                    name=skill_name,
                    category="Importada do curriculo",
                    proficiency="Nao informada",
                )
            )

        db.commit()
        return {
            "status": "PERFIL_IMPORTADO",
            "name": candidate.name,
            "filename": candidate.resume_filename,
            "experiences": len(parsed["experiences"]),
            "skills": len(parsed["skills"]),
            "education": len(parsed["education"]),
            "languages": len(parsed["languages"]),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/analyze-job")
def analyze(
    request: JobRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        candidate = _candidate_for_user(db, user)
        profile = _candidate_profile(candidate)
        analysis = analyze_job(
            f"{request.title}\n{request.description}",
            profile,
        )
        return {
            "candidate": profile["name"],
            "job_title": request.title,
            "analysis": analysis,
            "next_action": analysis["next_action"],
        }
    finally:
        db.close()


@app.post("/jobs")
def create_job(
    request: JobCreateRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        owner_id = _owner_id(user)
        stored_external_id = (
            f"{owner_id}:{request.external_id}"
            if owner_id is not None
            else request.external_id
        )
        existing = db.scalar(
            select(Job).where(Job.external_id == stored_external_id)
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Essa vaga jÃ¡ estÃ¡ cadastrada.",
            )

        job_data = request.model_dump()
        job_data["external_id"] = stored_external_id
        job = Job(owner_id=owner_id, **job_data)
        db.add(job)
        db.flush()

        candidate = _candidate_for_user(db, user)
        application = _ensure_application(db, job, candidate)
        quality = assess_job_capture(job_data)
        _save_capture_quality(application, quality)
        _apply_queue_decision(application, candidate, None)
        db.commit()
        db.refresh(job)
        db.refresh(application)

        return {
            "status": "VAGA_CADASTRADA",
            "job": {
                "id": job.id,
                "source": job.source,
                "external_id": job.external_id,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "modality": job.modality,
                "salary": job.salary,
                "url": job.url,
            },
            "application": {
                "id": application.id,
                "status": application.status,
            },
        }
    finally:
        db.close()


@app.post("/intake/text")
def intake_job_text(
    request: JobIntakeRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    try:
        parsed = parse_job_text(request.raw_text, request.source)
        quality = assess_job_capture(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db = SessionLocal()
    try:
        owner_id = _owner_id(user)
        stored_external_id = (
            f"{owner_id}:{parsed['external_id']}"
            if owner_id is not None
            else parsed["external_id"]
        )
        existing = db.scalar(
            select(Job).where(Job.external_id == stored_external_id)
        )
        if existing is not None:
            candidate = _candidate_for_user(db, user)
            application = _ensure_application(db, existing, candidate)
            _save_capture_quality(application, quality)
            analysis = None
            if request.reprocess_existing:
                existing.source = parsed["source"]
                existing.company = parsed["company"]
                existing.title = parsed["title"]
                existing.description = parsed["description"]
                for optional_field in ("location", "modality", "salary", "url"):
                    if parsed[optional_field]:
                        setattr(existing, optional_field, parsed[optional_field])

                if request.auto_analyze:
                    artifacts = _build_application(existing, candidate)
                    analysis = artifacts["analysis"]
                    _save_analysis(application, analysis, candidate)
                    if application.status in {"IDENTIFICADA", "ARQUIVADA"}:
                        _advance_application(
                            db,
                            application,
                            "ANALISADA",
                            "Vaga atualizada e reanalisada a partir de novo arquivo.",
                        )
                    else:
                        db.add(
                            ApplicationEvent(
                                application=application,
                                status=application.status,
                                note="Dados atualizados e score recalculado a partir de novo arquivo.",
                            )
                        )
            if analysis is None:
                _apply_queue_decision(application, candidate, None)
            db.commit()
            db.refresh(existing)
            db.refresh(application)
            return {
                "status": (
                    "VAGA_ATUALIZADA"
                    if request.reprocess_existing
                    else "VAGA_JA_EXISTIA"
                ),
                "duplicate": True,
                "updated": request.reprocess_existing,
                "job_id": existing.id,
                "application_id": application.id,
                "application_status": application.status,
                "company": existing.company,
                "job_title": existing.title,
                "location": existing.location,
                "modality": existing.modality,
                "url": existing.url,
                "analysis": analysis,
            }

        job_data = dict(parsed)
        job_data["external_id"] = stored_external_id
        job = Job(owner_id=owner_id, **job_data)
        db.add(job)
        db.flush()

        candidate = _candidate_for_user(db, user)
        application = _ensure_application(db, job, candidate)
        _save_capture_quality(application, quality)
        analysis = None
        if request.auto_analyze:
            artifacts = _build_application(job, candidate)
            analysis = artifacts["analysis"]
            _save_analysis(application, analysis, candidate)
            _advance_application(
                db,
                application,
                "ANALISADA",
                "Vaga captada e analisada automaticamente.",
            )
        else:
            _apply_queue_decision(application, candidate, None)

        db.commit()
        db.refresh(job)
        db.refresh(application)
        return {
            "status": "VAGA_CAPTADA",
            "duplicate": False,
            "job_id": job.id,
            "application_id": application.id,
            "application_status": application.status,
            "company": job.company,
            "job_title": job.title,
            "location": job.location,
            "modality": job.modality,
            "url": job.url,
            "analysis": analysis,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/intake/file")
async def intake_job_file(
    file: UploadFile = File(...),
    source: str = "print",
    auto_analyze: bool = True,
    user: dict[str, Any] = Depends(authenticated_user),
):
    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    if len(content) > MAX_JOB_FILE_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo excede 10 MB.")

    try:
        extracted = extract_job_file_text(content, file.filename or "")
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = intake_job_text(
        JobIntakeRequest(
            raw_text=extracted["text"],
            source=source,
            auto_analyze=auto_analyze,
            reprocess_existing=False,
        ),
        user,
    )
    result["extraction"] = {
        "method": extracted["method"],
        "filename": extracted["filename"],
        "characters": extracted["characters"],
    }
    return result


@app.post("/intake/file/preview")
async def preview_job_file(
    file: UploadFile = File(...),
    source: str = "print",
    user: dict[str, Any] = Depends(authenticated_user),
):
    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    if len(content) > MAX_JOB_FILE_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo excede 10 MB.")
    try:
        extracted = extract_job_file_text(content, file.filename or "")
        parsed = parse_job_text(extracted["text"], source)
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    enriched = infer_from_public_url(parsed)
    fetch_error = ""
    if parsed["url"]:
        try:
            structured = await run_in_threadpool(fetch_job_posting, parsed["url"])
        except SourceFetchError as exc:
            structured = None
            fetch_error = str(exc)
        if structured:
            enriched = dict(parsed)
            for field in (
                "title",
                "company",
                "description",
                "location",
                "modality",
                "salary",
                "url",
            ):
                if structured.get(field):
                    enriched[field] = structured[field]
            enriched["confidence"] = structured["confidence"]
            enriched["method"] = structured["method"]

    selected = enriched or dict(parsed)
    confidence = int(selected.get("confidence", 55))
    method = selected.get("method", "local_ocr")
    if confidence >= 85:
        confirmed = await run_in_threadpool(
            confirm_job_intake,
            JobIntakeConfirmRequest(
                external_id=parsed["external_id"],
                source=parsed["source"],
                company=selected["company"],
                title=selected["title"],
                location=selected["location"],
                modality=selected["modality"],
                salary=selected["salary"],
                url=selected["url"],
                description=selected["description"],
                auto_analyze=True,
            ),
            user,
        )
        confirmed.update(
            {
                "automatic": True,
                "confidence": confidence,
                "extraction_method": method,
            }
        )
        return confirmed

    return {
        "status": "REVISAO_NECESSARIA",
        "message": "A confianca ficou abaixo do limite automatico.",
        "external_id": parsed["external_id"],
        "source": parsed["source"],
        "company": selected["company"],
        "title": selected["title"],
        "location": selected["location"],
        "modality": selected["modality"],
        "salary": selected["salary"],
        "url": selected["url"],
        "description": selected["description"],
        "confidence": confidence,
        "extraction_method": method,
        "fetch_error": fetch_error,
        "extraction": {
            "method": extracted["method"],
            "filename": extracted["filename"],
            "characters": extracted["characters"],
        },
    }


@app.post("/intake/confirm")
def confirm_job_intake(
    request: JobIntakeConfirmRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    if not re.fullmatch(r"intake-[0-9a-f]{24}", request.external_id):
        raise HTTPException(status_code=422, detail="Identificador da captura invalido.")
    if len(request.title.strip()) < 3 or len(request.company.strip()) < 2:
        raise HTTPException(status_code=422, detail="Confira o cargo e a empresa.")
    if len(request.description.strip()) < 60:
        raise HTTPException(status_code=422, detail="A descricao possui pouco conteudo.")

    db = SessionLocal()
    try:
        owner_id = _owner_id(user)
        stored_external_id = (
            f"{owner_id}:{request.external_id}"
            if owner_id is not None
            else request.external_id
        )
        job = db.scalar(select(Job).where(Job.external_id == stored_external_id))
        updated = job is not None
        values = {
            "source": request.source.strip()[:50],
            "company": request.company.strip()[:200],
            "title": request.title.strip()[:200],
            "location": request.location.strip()[:200],
            "modality": request.modality.strip()[:50],
            "salary": request.salary.strip()[:100],
            "url": request.url.strip()[:1000],
            "description": request.description.strip(),
        }
        if job is None:
            job = Job(
                owner_id=owner_id,
                external_id=stored_external_id,
                **values,
            )
            db.add(job)
            db.flush()
        else:
            for field, value in values.items():
                setattr(job, field, value)

        candidate = _candidate_for_user(db, user)
        application = _ensure_application(db, job, candidate)
        quality = assess_job_capture(values)
        _save_capture_quality(application, quality)
        analysis = None
        if request.auto_analyze:
            artifacts = _build_application(job, candidate)
            analysis = artifacts["analysis"]
            _save_analysis(application, analysis, candidate)
            if application.status in {"IDENTIFICADA", "ARQUIVADA"}:
                _advance_application(
                    db,
                    application,
                    "ANALISADA",
                    "Dados revisados, confirmados e analisados.",
                )
            elif updated:
                db.add(
                    ApplicationEvent(
                        application=application,
                        status=application.status,
                        note="Dados revisados e score recalculado.",
                    )
                )
            else:
                _advance_application(
                    db,
                    application,
                    "ANALISADA",
                    "Vaga confirmada e analisada automaticamente.",
                )
        else:
            _apply_queue_decision(application, candidate, None)

        db.commit()
        db.refresh(job)
        db.refresh(application)
        return {
            "status": "VAGA_ATUALIZADA" if updated else "VAGA_CAPTADA",
            "updated": updated,
            "job_id": job.id,
            "application_id": application.id,
            "application_status": application.status,
            "company": job.company,
            "job_title": job.title,
            "analysis": analysis,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/jobs")
def list_jobs(
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        query = select(Job).order_by(Job.id.desc())
        owner_id = _owner_id(user)
        if owner_id is not None:
            query = query.where(Job.owner_id == owner_id)
        jobs = db.scalars(query).all()
        return {
            "total": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "source": job.source,
                    "external_id": job.external_id,
                    "company": job.company,
                    "title": job.title,
                    "location": job.location,
                    "modality": job.modality,
                    "salary": job.salary,
                    "url": job.url,
                }
                for job in jobs
            ],
        }
    finally:
        db.close()


@app.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        job = _job_for_user(db, job_id, user)
        if job is None:
            raise HTTPException(status_code=404, detail="Vaga nÃ£o encontrada.")

        return {
            "id": job.id,
            "source": job.source,
            "external_id": job.external_id,
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "modality": job.modality,
            "salary": job.salary,
            "url": job.url,
            "description": job.description,
        }
    finally:
        db.close()


@app.get("/applications")
def list_applications(
    status: str | None = None,
    decision: str | None = None,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        if status is not None and status not in APPLICATION_STATUSES:
            raise HTTPException(
                status_code=422,
                detail="Status de candidatura invÃ¡lido.",
            )
        if decision is not None and decision not in {
            "AUTOMATICA",
            "REVISAR",
            "DESCARTAR",
        }:
            raise HTTPException(
                status_code=422,
                detail="Decisao da fila invalida.",
            )

        query = (
            select(Application)
            .join(Application.job)
            .order_by(Application.updated_at.desc())
        )
        owner_id = _owner_id(user)
        if owner_id is not None:
            query = query.where(Job.owner_id == owner_id)
        if status is not None:
            query = query.where(Application.status == status)
        if decision is not None:
            query = query.where(Application.queue_decision == decision)

        applications = db.scalars(query).all()
        return {
            "total": len(applications),
            "applications": [
                _serialize_application(application)
                for application in applications
            ],
        }
    finally:
        db.close()


@app.get("/applications/{application_id}")
def get_application(
    application_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(
                status_code=404,
                detail="Candidatura nÃ£o encontrada.",
            )
        return _serialize_application(application)
    finally:
        db.close()


@app.get(
    "/applications/{application_id}/document",
    response_class=FileResponse,
)
def download_application_document(
    application_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(
                status_code=404,
                detail="Candidatura nÃ£o encontrada.",
            )
        if not application.document_path:
            raise HTTPException(
                status_code=404,
                detail="Essa candidatura ainda nÃ£o possui currÃ­culo gerado.",
            )

        document_path = Path(application.document_path).resolve()
        if not document_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="O arquivo do currÃ­culo nÃ£o foi encontrado.",
            )

        return FileResponse(
            path=document_path,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            filename=document_path.name,
        )
    finally:
        db.close()


@app.patch("/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    request: ApplicationStatusRequest,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(
                status_code=404,
                detail="Candidatura nÃ£o encontrada.",
            )

        if application.status != request.status or request.note:
            _add_application_event(
                db,
                application,
                request.status,
                request.note,
            )
        db.commit()
        db.refresh(application)
        return _serialize_application(application)
    finally:
        db.close()


@app.post("/jobs/{job_id}/analyze")
def analyze_saved_job(
    job_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        job = _job_for_user(db, job_id, user)
        if job is None:
            raise HTTPException(status_code=404, detail="Vaga nÃ£o encontrada.")

        candidate = _candidate_for_user(db, user)
        artifacts = _build_application(job, candidate)
        analysis = artifacts["analysis"]
        application = _ensure_application(db, job, candidate)
        _save_analysis(application, analysis, candidate)
        _advance_application(
            db,
            application,
            "ANALISADA",
            "AnÃ¡lise e score calculados.",
        )
        db.commit()
        db.refresh(application)

        return {
            "job_id": job.id,
            "application_id": application.id,
            "application_status": application.status,
            "candidate": artifacts["profile"]["name"],
            "company": job.company,
            "job_title": job.title,
            "analysis": analysis,
            "next_action": analysis["next_action"],
        }
    finally:
        db.close()

@app.post("/jobs/{job_id}/cover-letter")
def create_cover_letter_for_job(
    job_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        job = _job_for_user(db, job_id, user)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Vaga nÃ£o encontrada.",
            )

        candidate = _candidate_for_user(db, user)

        artifacts = _build_application(
            job,
            candidate,
        )

        letter = generate_cover_letter(
            job_title=job.title,
            company=job.company,
            profile=artifacts["profile"],
            analysis=artifacts["analysis"],
            personalization=artifacts["personalization"],
        )

        application = _ensure_application(db, job, candidate)
        _save_analysis(application, artifacts["analysis"], candidate)
        application.cover_letter_text = letter
        db.commit()
        db.refresh(application)

        return {
            "job_id": job.id,
            "application_id": application.id,
            "company": job.company,
            "job_title": job.title,
            "candidate": artifacts["profile"]["name"],
            "analysis_score": artifacts["analysis"]["score"],
            "personalization_score": artifacts[
                "personalization"
            ]["personalization_score"],
            "letter": letter,
        }

    finally:
        db.close()

@app.post(
    "/jobs/{job_id}/cover-letter/document",
    response_class=FileResponse,
)
def create_cover_letter_document(
    job_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        job = _job_for_user(db, job_id, user)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Vaga nÃ£o encontrada.",
            )

        candidate = _candidate_for_user(db, user)

        artifacts = _build_application(
            job,
            candidate,
        )

        letter = generate_cover_letter(
            job_title=job.title,
            company=job.company,
            profile=artifacts["profile"],
            analysis=artifacts["analysis"],
            personalization=artifacts["personalization"],
        )

        output_path = Path(
            generate_cover_letter_docx(
                letter=letter,
                company=job.company,
                job_title=job.title,
            )
        ).resolve()

        if not output_path.is_file():
            raise HTTPException(
                status_code=500,
                detail="A carta nÃ£o foi criada.",
            )

        application = _ensure_application(db, job, candidate)
        _save_analysis(application, artifacts["analysis"], candidate)
        application.cover_letter_text = letter
        application.cover_letter_path = str(output_path)
        db.add(
            ApplicationEvent(
                application_id=application.id,
                status=application.status,
                note="Carta de apresentaÃ§Ã£o gerada.",
            )
        )
        db.commit()

        return FileResponse(
            path=output_path,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            filename=output_path.name,
        )

    finally:
        db.close()


@app.get(
    "/applications/{application_id}/cover-letter/document",
    response_class=FileResponse,
)
def download_application_cover_letter(
    application_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    db = SessionLocal()

    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(
                status_code=404,
                detail="Candidatura nÃ£o encontrada.",
            )
        if not application.cover_letter_path:
            raise HTTPException(
                status_code=404,
                detail="Essa candidatura ainda nÃ£o possui carta gerada.",
            )

        document_path = Path(application.cover_letter_path).resolve()
        if not document_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="O arquivo da carta nÃ£o foi encontrado.",
            )

        return FileResponse(
            path=document_path,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            filename=document_path.name,
        )
    finally:
        db.close()
        
@app.post("/jobs/{job_id}/generate-document", response_class=FileResponse)
def generate_document_for_job(
    job_id: int,
    user: dict[str, Any] = Depends(authenticated_user),
):
    """Analisa a vaga, personaliza o currÃ­culo e devolve o DOCX para download."""
    db = SessionLocal()

    try:
        job = _job_for_user(db, job_id, user)
        if job is None:
            raise HTTPException(status_code=404, detail="Vaga nÃ£o encontrada.")

        candidate = _candidate_for_user(db, user)
        artifacts = _build_application(job, candidate)
        output_path = Path(generate_docx(artifacts["resume"])).resolve()

        if not output_path.is_file():
            raise HTTPException(
                status_code=500,
                detail="O documento nÃ£o foi criado.",
            )

        application = _ensure_application(db, job, candidate)
        _save_analysis(application, artifacts["analysis"], candidate)
        application.personalization_score = artifacts[
            "personalization"
        ]["personalization_score"]
        application.document_path = str(output_path)
        _advance_application(
            db,
            application,
            "CURRICULO_GERADO",
            "CurrÃ­culo personalizado e documento DOCX gerado.",
        )
        db.commit()

        return FileResponse(
            path=output_path,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            filename=output_path.name,
            headers={
                "X-Application-Id": str(application.id),
                "X-Application-Status": application.status,
                "X-Analysis-Score": str(artifacts["analysis"]["score"]),
                "X-Personalization-Score": str(
                    artifacts["personalization"]["personalization_score"]
                ),
            },
        )
    finally:
        db.close()


@app.post("/generate-document")
def generate_document(request: ResumeRequest):
    resume = request.resume.copy()
    resume["target"] = request.title
    output_path = generate_docx(resume)

    return {
        "status": "DOCUMENTO_GERADO",
        "candidate": resume.get("candidate", {}).get("name", "Candidato"),
        "job_title": request.title,
        "file": output_path,
    }

app.include_router(queue_router)

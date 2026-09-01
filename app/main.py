import json
import base64
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select, text
from starlette.concurrency import run_in_threadpool

from .auth import AuthMiddleware, authenticated_user, router as auth_router
from .gmail_integration import router as gmail_router
from .gmail_monitor import router as gmail_monitor_router, start_monitor, stop_monitor
from .queue_routes import router as queue_router
from .analyzer import analyze_job
from .cover_letter import generate_cover_letter, generate_cover_letter_docx
from .decision_engine import decide_opportunity, normalize_preferences
from .database import Base, SessionLocal, engine
from .job_intake import parse_job_text
from .job_quality import assess_job_capture
from .job_source_fetcher import SourceFetchError, fetch_job_posting, infer_from_public_url
from .job_file_intake import MAX_JOB_FILE_BYTES, OCRUnavailableError, extract_job_file_text
from .models import Application, ApplicationEvent, Candidate, Experience, Job, Skill
from .resume_importer import MAX_UPLOAD_BYTES, parse_resume
from .resume_document import MASTER_PROFILE, generate_docx
from .resume_generator import generate_resume
from .resume_personalizer import personalize_resume
from .queue_service import enqueue

app = FastAPI(title="Agente de Candidaturas", version="0.24.0")
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(gmail_router)
app.include_router(gmail_monitor_router)
app.include_router(queue_router)

APPLICATION_STATUSES = ("IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA")
DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"
LANDING_PATH = Path(__file__).parent / "static" / "landing.html"
SETTINGS_PATH = Path(__file__).parent / "static" / "settings.html"
PROFILE_PAGE_PATH = Path(__file__).parent / "static" / "profile.html"
SECURITY_PAGE_PATH = Path(__file__).parent / "static" / "security.html"
ONBOARDING_PATH = Path(__file__).parent / "static" / "onboarding.html"
RESUMES_PATH = Path(__file__).parent / "static" / "curriculos.html"
CONFIG_PATH = Path(__file__).parent / "static" / "configuracoes.html"
JOBS_PAGE_PATH = Path(__file__).parent / "static" / "vagas.html"
APPLICATIONS_PAGE_PATH = Path(__file__).parent / "static" / "candidaturas.html"
INTERVIEWS_PAGE_PATH = Path(__file__).parent / "static" / "entrevistas.html"
SIMULATOR_PAGE_PATH = Path(__file__).parent / "static" / "simulador.html"

def _owner_id(user): return user.get("id") if isinstance(user, dict) else None
def _candidate_for_user(db, user):
    q = select(Candidate).order_by(Candidate.id)
    oid = _owner_id(user)
    if oid: q = q.where(Candidate.owner_id == oid)
    c = db.scalar(q)
    if oid and c is None: raise HTTPException(409, "Perfil do candidato nao configurado.")
    return c
def _job_for_user(db, job_id, user):
    q = select(Job).where(Job.id == job_id)
    oid = _owner_id(user)
    if oid: q = q.where(Job.owner_id == oid)
    return db.scalar(q)
def _application_for_user(db, app_id, user):
    q = select(Application).join(Application.job).where(Application.id == app_id)
    oid = _owner_id(user)
    if oid: q = q.where(Job.owner_id == oid)
    return db.scalar(q)

class JobRequest(BaseModel): title: str; description: str
class JobCreateRequest(BaseModel): source: str = "manual"; external_id: str; company: str; title: str; location: str = ""; modality: str = ""; salary: str = ""; url: str = ""; description: str
class JobIntakeRequest(BaseModel): raw_text: str; source: str = "texto"; auto_analyze: bool = True; reprocess_existing: bool = False
class JobIntakeConfirmRequest(BaseModel): external_id: str; source: str = "print"; company: str; title: str; location: str = ""; modality: str = ""; salary: str = ""; url: str = ""; description: str; auto_analyze: bool = True
class ResumeRequest(BaseModel): title: str; resume: dict
class ApplicationStatusRequest(BaseModel): status: Literal["IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"]; note: str = ""
class CandidatePreferencesRequest(BaseModel): target_roles: list[str] = []; locations: list[str] = []; modalities: list[str] = []; contract_types: list[str] = []; schedules: list[str] = []; industries: list[str] = []; excluded_companies: list[str] = []; required_keywords: list[str] = []; excluded_keywords: list[str] = []; salary_min: int | None = None; salary_max: int | None = None; minimum_score: int = 65; automatic_score: int = 85; allow_automatic: bool = False; max_daily_applications: int = 5
class ProfileUpdateRequest(BaseModel): name: str; headline: str = ""; summary: str = ""; location: str = ""; phone: str = ""; linkedin: str = ""; website: str = ""; industry: str = ""; target_roles: list[str] = []; profile_data: dict[str, Any] = Field(default_factory=dict)

def _split_target_roles(s): return [x.strip() for x in s.split(",") if x.strip()]
def _fallback_profile():
    exps = [{"company": e["company"], "role": e["role"], "description": " ".join(e["bullets"])} for e in MASTER_PROFILE["experiences"]]
    return {"name": MASTER_PROFILE["name"], "summary": MASTER_PROFILE["summary"], "target_roles": ["Analista de RH", "Analista de DP", "Supervisor de RH", "Supervisor de DP", "Coordenador de RH", "Coordenador de DP", "Gerente de RH", "Gerente de DP"], "experience_texts": [e["description"] for e in exps], "experiences": exps, "skills": list(MASTER_PROFILE["skills"]), "location": MASTER_PROFILE["location"], "contact": {"phone": MASTER_PROFILE["phone"], "email": MASTER_PROFILE["email"], "linkedin": MASTER_PROFILE["linkedin"], "location": MASTER_PROFILE["location"]}}
def _candidate_profile(cand):
    if cand is None: return _fallback_profile()
    pd = {}
    if cand.profile_data:
        try: pd = json.loads(cand.profile_data)
        except: pass
    exps = [{"company": e.company, "role": e.role, "description": e.description, "start_date": e.start_date, "end_date": e.end_date, "period": " - ".join([v for v in (e.start_date, e.end_date) if v]), "bullets": [l.strip() for l in e.description.splitlines() if l.strip()]} for e in cand.experiences]
    return {"name": cand.name, "summary": cand.summary, "target_roles": _split_target_roles(cand.target_roles), "experience_texts": [e["description"] for e in exps], "experiences": exps, "skills": [s.name for s in cand.skills], "headline": pd.get("headline", ""), "education": pd.get("education", []), "languages": pd.get("languages", []), "location": cand.location, "contact": {"phone": cand.phone, "email": cand.email, "linkedin": cand.linkedin, "location": cand.location}}
def _job_text(j): return "\n".join([j.title or "", j.company or "", j.location or "", j.modality or "", j.salary or "", j.description or ""])
def _build_application(job, cand):
    p = _candidate_profile(cand)
    a = analyze_job(_job_text(job), p)
    pers = personalize_resume(job.title, job.description, p)
    rc = {"name": p["name"], "contact": p["contact"], "target": job.title, "headline": p.get("headline", ""), "skills": p.get("skills", []), "education": p.get("education", []), "languages": p.get("languages", [])}
    r = generate_resume(rc, pers)
    r["target"] = job.title
    return {"profile": p, "analysis": a, "personalization": pers, "resume": r}
def _add_event(db, app, status, note=""):
    app.status = status
    db.add(ApplicationEvent(application_id=app.id, status=status, note=note or None))
def _ensure_app(db, job, cand):
    a = db.scalar(select(Application).where(Application.job_id == job.id))
    if a: return a
    a = Application(job_id=job.id, candidate_id=cand.id if cand else None, status="IDENTIFICADA")
    db.add(a); db.flush()
    _add_event(db, a, "IDENTIFICADA", "Vaga adicionada.")
    return a
def _advance_app(db, app, status, note=""):
    if APPLICATION_STATUSES.index(status) > APPLICATION_STATUSES.index(app.status):
        _add_event(db, app, status, note)
def _serialize_app(a):
    an = None
    if a.analysis_data:
        try: an = json.loads(a.analysis_data)
        except: pass
    try: dr = json.loads(a.decision_reasons or "[]")
    except: dr = []
    try: fc = json.loads(a.field_confidence or "{}")
    except: fc = {}
    return {"id": a.id, "job_id": a.job_id, "candidate_id": a.candidate_id, "company": a.job.company, "job_title": a.job.title, "status": a.status, "analysis_score": a.analysis_score, "personalization_score": a.personalization_score, "recommendation": a.recommendation, "queue_decision": a.queue_decision or "REVISAR", "decision_reasons": dr, "capture_confidence": a.capture_confidence, "field_confidence": fc, "analysis": an, "document_path": a.document_path, "cover_letter_text": a.cover_letter_text, "cover_letter_path": a.cover_letter_path, "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(), "events": [{"id": e.id, "status": e.status, "note": e.note, "created_at": e.created_at.isoformat()} for e in a.events]}
def _cand_prefs(cand):
    s = {}
    if cand and cand.preferences_data:
        try: s = json.loads(cand.preferences_data)
        except: pass
    return normalize_preferences(s, target_roles=cand.target_roles if cand else "", location=cand.location if cand else "")
def _apply_decision(app, cand, analysis):
    r = decide_opportunity({"title": app.job.title, "company": app.job.company, "location": app.job.location, "modality": app.job.modality, "description": app.job.description}, analysis, _cand_prefs(cand), capture_confidence=app.capture_confidence)
    app.queue_decision = r["decision"]
    app.decision_reasons = json.dumps(r["reasons"], ensure_ascii=False)
def _save_quality(app, q):
    app.capture_confidence = int(q["confidence"])
    app.field_confidence = json.dumps(q["field_confidence"], ensure_ascii=False)
def _save_analysis(app, analysis, cand):
    app.analysis_score = analysis["score"]
    app.recommendation = analysis["recommendation"]
    app.analysis_data = json.dumps(analysis, ensure_ascii=False)
    _apply_decision(app, cand, analysis)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for col in ["owner_id", "profile_data", "resume_filename", "preferences_data"]:
            if col not in {c["name"] for c in inspect(engine).get_columns("candidates")}:
                db.execute(text(f"ALTER TABLE candidates ADD COLUMN {col} {'VARCHAR(36)' if col == 'owner_id' else 'TEXT'}"))
        if "owner_id" not in {c["name"] for c in inspect(engine).get_columns("jobs")}:
            db.execute(text("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36)"))
        for col in ["cover_letter_text", "cover_letter_path", "analysis_data", "decision_reasons", "field_confidence"]:
            if col not in {c["name"] for c in inspect(engine).get_columns("applications")}:
                db.execute(text(f"ALTER TABLE applications ADD COLUMN {col} TEXT"))
        if "queue_decision" not in {c["name"] for c in inspect(engine).get_columns("applications")}:
            db.execute(text("ALTER TABLE applications ADD COLUMN queue_decision VARCHAR(20) DEFAULT 'REVISAR' NOT NULL"))
        if "capture_confidence" not in {c["name"] for c in inspect(engine).get_columns("applications")}:
            db.execute(text("ALTER TABLE applications ADD COLUMN capture_confidence INTEGER"))
        for idx in ["idx_applications_status", "idx_applications_updated_at", "idx_applications_queue_decision", "idx_candidates_owner_id", "idx_jobs_owner_id"]:
            db.execute(text(f"CREATE INDEX IF NOT EXISTS {idx} ON {'applications' if 'applications' in idx else 'candidates' if 'candidates' in idx else 'jobs'} ({'status' if 'status' in idx else 'updated_at' if 'updated' in idx else 'queue_decision' if 'queue' in idx else 'owner_id'})"))
        for job in db.scalars(select(Job)).all():
            cand = db.scalar(select(Candidate).where(Candidate.owner_id == job.owner_id).order_by(Candidate.id))
            _ensure_app(db, job, cand)
        db.commit()
    finally:
        db.close()
    start_monitor()

@app.on_event("shutdown")
async def shutdown():
    await stop_monitor()

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    if not LANDING_PATH.is_file():
        return {"agente": "Agente de Candidaturas", "status": "online", "version": "0.24.0", "dashboard": "/dashboard"}
    return HTMLResponse(LANDING_PATH.read_text(encoding="utf-8"))

@app.get("/health", include_in_schema=False)
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "healthy"}

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    if not DASHBOARD_PATH.is_file(): raise HTTPException(500, "Dashboard nao encontrado.")
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))

@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page():
    if not CONFIG_PATH.is_file(): raise HTTPException(500, "Configuracoes nao encontradas.")
    return HTMLResponse(CONFIG_PATH.read_text(encoding="utf-8"))

@app.get("/perfil", response_class=HTMLResponse, include_in_schema=False)
def profile_page():
    if not PROFILE_PAGE_PATH.is_file(): raise HTTPException(500, "Perfil nao encontrado.")
    return HTMLResponse(PROFILE_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/seguranca", response_class=HTMLResponse, include_in_schema=False)
def security_page():
    if not SECURITY_PAGE_PATH.is_file(): raise HTTPException(500, "Seguranca nao encontrada.")
    return HTMLResponse(SECURITY_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/onboarding", response_class=HTMLResponse, include_in_schema=False)
def onboarding_page():
    if not ONBOARDING_PATH.is_file(): raise HTTPException(500, "Onboarding nao encontrado.")
    return HTMLResponse(ONBOARDING_PATH.read_text(encoding="utf-8"))

@app.get("/curriculos", response_class=HTMLResponse, include_in_schema=False)
def resumes_page():
    if not RESUMES_PATH.is_file(): raise HTTPException(500, "Curriculos nao encontrados.")
    return HTMLResponse(RESUMES_PATH.read_text(encoding="utf-8"))

@app.get("/configuracoes", response_class=HTMLResponse, include_in_schema=False)
def config_page():
    if not CONFIG_PATH.is_file(): raise HTTPException(500, "Configuracoes nao encontradas.")
    return HTMLResponse(CONFIG_PATH.read_text(encoding="utf-8"))

@app.get("/vagas", response_class=HTMLResponse, include_in_schema=False)
def jobs_page():
    if not JOBS_PAGE_PATH.is_file(): raise HTTPException(500, "Vagas nao encontradas.")
    return HTMLResponse(JOBS_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/candidaturas", response_class=HTMLResponse, include_in_schema=False)
def applications_page():
    if not APPLICATIONS_PAGE_PATH.is_file(): raise HTTPException(500, "Candidaturas nao encontradas.")
    return HTMLResponse(APPLICATIONS_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/entrevistas", response_class=HTMLResponse, include_in_schema=False)
def interviews_page():
    if not INTERVIEWS_PAGE_PATH.is_file(): raise HTTPException(500, "Entrevistas nao encontradas.")
    return HTMLResponse(INTERVIEWS_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/simulador", response_class=HTMLResponse, include_in_schema=False)
def simulator_page():
    if not SIMULATOR_PAGE_PATH.is_file(): raise HTTPException(500, "Simulador nao encontrado.")
    return HTMLResponse(SIMULATOR_PAGE_PATH.read_text(encoding="utf-8"))

@app.get("/profile")
def get_profile(user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        c = _candidate_for_user(db, user)
        if c is None: return {"configured": False}
        data = {}
        if c.profile_data:
            try: data = json.loads(c.profile_data)
            except: data = {}
        return {"configured": True, "name": c.name, "location": c.location, "email": c.email, "phone": c.phone, "linkedin": c.linkedin, "target_roles": _split_target_roles(c.target_roles), "summary": c.summary, "headline": data.get("headline", ""), "website": data.get("website", ""), "industry": data.get("industry", ""), "photo_data": data.get("photo_data", ""), "resume_filename": c.resume_filename, "experiences": len(c.experiences), "skills": len(c.skills)}
    finally: db.close()

@app.put("/profile")
def update_profile(req: ProfileUpdateRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        c = db.scalar(select(Candidate).where(Candidate.owner_id == oid).order_by(Candidate.id))
        if c is None:
            c = Candidate(owner_id=oid, name=req.name.strip() or "Usuário", location=req.location.strip(), email=user.get("email", ""), phone=req.phone.strip(), linkedin=req.linkedin.strip(), target_roles=", ".join(req.target_roles), summary=req.summary.strip())
            db.add(c)
        else:
            c.name = req.name.strip() or c.name; c.location = req.location.strip(); c.phone = req.phone.strip(); c.linkedin = req.linkedin.strip(); c.target_roles = ", ".join(req.target_roles); c.summary = req.summary.strip()
        data = {}
        if c.profile_data:
            try: data = json.loads(c.profile_data)
            except: data = {}
        data.update(req.profile_data)
        data.update({"headline": req.headline.strip(), "website": req.website.strip(), "industry": req.industry.strip()})
        c.profile_data = json.dumps(data, ensure_ascii=False)
        db.commit()
        return {"status": "PERFIL_ATUALIZADO"}
    except Exception:
        db.rollback(); raise
    finally: db.close()

@app.post("/profile/photo")
async def upload_profile_photo(file: UploadFile = File(...), user=Depends(authenticated_user)):
    content = await file.read()
    if len(content) > 1_500_000: raise HTTPException(413, "A foto deve ter no máximo 1,5 MB.")
    content_type = (file.content_type or "").lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}: raise HTTPException(415, "Use uma imagem JPG, PNG ou WebP.")
    db = SessionLocal()
    try:
        c = db.scalar(select(Candidate).where(Candidate.owner_id == _owner_id(user)).order_by(Candidate.id))
        if c is None: raise HTTPException(409, "Salve seu perfil antes de adicionar uma foto.")
        data = {}
        if c.profile_data:
            try: data = json.loads(c.profile_data)
            except: data = {}
        data["photo_data"] = f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
        c.profile_data = json.dumps(data, ensure_ascii=False); db.commit()
        return {"status": "FOTO_ATUALIZADA"}
    finally: db.close()

@app.get("/preferences")
def get_preferences(user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        c = _candidate_for_user(db, user)
        if c is None: raise HTTPException(409, "Importe o curriculo primeiro.")
        return _cand_prefs(c)
    finally: db.close()

@app.put("/preferences")
def update_preferences(req: CandidatePreferencesRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        c = _candidate_for_user(db, user)
        if c is None: raise HTTPException(409, "Importe o curriculo primeiro.")
        prefs = normalize_preferences(req.model_dump())
        c.preferences_data = json.dumps(prefs, ensure_ascii=False)
        apps = db.scalars(select(Application).join(Application.job).where(Job.owner_id == _owner_id(user))).all()
        changed = 0
        for a in apps:
            prev = a.queue_decision
            an = None
            if a.analysis_data:
                try: an = json.loads(a.analysis_data)
                except: pass
            _apply_decision(a, c, an)
            if prev != a.queue_decision:
                changed += 1
                db.add(ApplicationEvent(application=a, status=a.status, note=f"Decisao recalculada: {a.queue_decision}."))
        db.commit()
        return {"status": "PREFERENCIAS_ATUALIZADAS", "preferences": prefs, "decisions_updated": changed}
    except: db.rollback(); raise
    finally: db.close()

@app.post("/profile/resume")
async def upload_resume(file: UploadFile = File(...), user=Depends(authenticated_user)):
    filename = Path((file.filename or "curriculo.docx").replace("\\", "/")).name
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    try: parsed = parse_resume(content, filename)
    except ValueError as e: raise HTTPException(422, str(e))
    oid = _owner_id(user)
    if oid is None: raise HTTPException(409, "Importacao disponivel somente no modo autenticado.")
    db = SessionLocal()
    try:
        c = db.scalar(select(Candidate).where(Candidate.owner_id == oid))
        if c is None:
            c = Candidate(owner_id=oid, name=parsed["name"], location=parsed["location"], email=parsed["email"], phone=parsed["phone"], linkedin=parsed["linkedin"], target_roles=parsed["target_roles"], summary=parsed["summary"])
            db.add(c); db.flush()
        else:
            c.name = parsed["name"]; c.location = parsed["location"]; c.email = parsed["email"]; c.phone = parsed["phone"]; c.linkedin = parsed["linkedin"]; c.target_roles = parsed["target_roles"]; c.summary = parsed["summary"]; c.experiences.clear(); c.skills.clear()
        c.profile_data = json.dumps({"headline": parsed["headline"], "education": parsed["education"], "languages": parsed["languages"]}, ensure_ascii=False)
        c.resume_filename = parsed["source_filename"]
        for item in parsed["experiences"]:
            c.experiences.append(Experience(company=item["company"], role=item["role"], start_date=item["start_date"], end_date=item["end_date"], description=item["description"]))
        for skill in parsed["skills"]:
            c.skills.append(Skill(name=skill, category="Importada", proficiency="Nao informada"))
        db.commit()
        return {"status": "PERFIL_IMPORTADO", "name": c.name, "filename": c.resume_filename, "experiences": len(parsed["experiences"]), "skills": len(parsed["skills"]), "education": len(parsed["education"]), "languages": len(parsed["languages"])}
    except: db.rollback(); raise
    finally: db.close()

@app.post("/analyze-job")
def analyze_job_endpoint(req: JobRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        c = _candidate_for_user(db, user)
        profile = _candidate_profile(c)
        analysis = analyze_job(f"{req.title}\n{req.description}", profile)
        return {"candidate": profile["name"], "job_title": req.title, "analysis": analysis, "next_action": analysis["next_action"]}
    finally: db.close()

@app.post("/jobs")
def create_job(req: JobCreateRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        ext_id = f"{oid}:{req.external_id}" if oid else req.external_id
        if db.scalar(select(Job).where(Job.external_id == ext_id)): raise HTTPException(409, "Vaga ja cadastrada.")
        data = req.model_dump(); data["external_id"] = ext_id
        job = Job(owner_id=oid, **data)
        db.add(job); db.flush()
        c = _candidate_for_user(db, user)
        app = _ensure_app(db, job, c)
        quality = assess_job_capture(data)
        _save_quality(app, quality)
        _apply_decision(app, c, None)
        db.commit(); db.refresh(job); db.refresh(app)
        return {"status": "VAGA_CADASTRADA", "job": {"id": job.id, "source": job.source, "external_id": job.external_id, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "salary": job.salary, "url": job.url}, "application": {"id": app.id, "status": app.status}}
    finally: db.close()

@app.post("/intake/text")
def intake_text(req: JobIntakeRequest, user=Depends(authenticated_user)):
    try:
        parsed = parse_job_text(req.raw_text, req.source)
        quality = assess_job_capture(parsed)
    except ValueError as e:
        raise HTTPException(422, str(e))
    
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        ext_id = f"{oid}:{parsed['external_id']}" if oid else parsed["external_id"]
        existing = db.scalar(select(Job).where(Job.external_id == ext_id))
        
        if existing:
            c = _candidate_for_user(db, user)
            app = _ensure_app(db, existing, c)
            _save_quality(app, quality)
            analysis = None
            if req.reprocess_existing:
                existing.source = parsed["source"]
                existing.company = parsed["company"]
                existing.title = parsed["title"]
                existing.description = parsed["description"]
                for f in ("location", "modality", "salary", "url"):
                    if parsed[f]:
                        setattr(existing, f, parsed[f])
                if req.auto_analyze:
                    arts = _build_application(existing, c)
                    analysis = arts["analysis"]
                    _save_analysis(app, analysis, c)
                    if app.status in ("IDENTIFICADA", "ARQUIVADA"):
                        _advance_app(db, app, "ANALISADA", "Vaga atualizada e reanalisada.")
                    else:
                        db.add(ApplicationEvent(application=app, status=app.status, note="Dados atualizados e score recalculado."))
            if analysis is None:
                _apply_decision(app, c, None)
            db.commit()
            db.refresh(existing)
            db.refresh(app)
            return {
                "status": "VAGA_ATUALIZADA" if req.reprocess_existing else "VAGA_JA_EXISTIA",
                "duplicate": True,
                "updated": req.reprocess_existing,
                "job_id": existing.id,
                "application_id": app.id,
                "application_status": app.status,
                "company": existing.company,
                "job_title": existing.title,
                "location": existing.location,
                "modality": existing.modality,
                "url": existing.url,
                "analysis": analysis
            }
        
        # USAR A FILA
        from .queue_service import enqueue
        
        captured_data = {
            "title": parsed.get("title"),
            "company": parsed.get("company"),
            "location": parsed.get("location"),
            "modality": parsed.get("modality"),
            "url": parsed.get("url"),
            "description": parsed.get("description"),
            "raw_excerpt": req.raw_text[:2000],
            "confidence_title": quality.get("field_confidence", {}).get("title"),
            "confidence_company": quality.get("field_confidence", {}).get("company"),
            "confidence_description": quality.get("field_confidence", {}).get("description"),
            "confidence_url": quality.get("field_confidence", {}).get("url"),
            "confidence_overall": quality.get("confidence"),
            "health_score": quality.get("health", {}).get("score"),
            "health_band": quality.get("health", {}).get("band"),
            "health_signals": quality.get("health", {}).get("signals", []),
            "fraud_suspected": quality.get("health", {}).get("fraud_suspected", False),
        }
        
        decision_result = {
            "decision": quality.get("decision", "REVISAR"),
            "reasons": quality.get("reasons", []),
            "engine_version": "0.24.0",
            "score": None,
        }
        
        item, created = enqueue(
            session=db,
            owner_id=oid or "local_user",
            captured=captured_data,
            decision_result=decision_result,
            source="texto",
            source_ref=parsed.get("external_id"),
        )
        db.commit()
        
        job_id = item.job_id
        application = None
        if job_id:
            job = db.scalar(select(Job).where(Job.id == job_id))
            if job:
                c = _candidate_for_user(db, user)
                application = _ensure_app(db, job, c)
                db.commit()
                db.refresh(application)
        
        return {
            "status": "VAGA_ENFILEIRADA",
            "duplicate": False,
            "queue_item_id": item.id,
            "queue_decision": item.decision,
            "queue_status": item.status,
            "job_id": job_id,
            "application_id": application.id if application else None,
            "company": parsed.get("company"),
            "job_title": parsed.get("title"),
            "location": parsed.get("location"),
            "modality": parsed.get("modality"),
            "url": parsed.get("url"),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.post("/intake/file")
async def intake_file(file: UploadFile = File(...), source: str = "print", auto_analyze: bool = True, user=Depends(authenticated_user)):
    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    if len(content) > MAX_JOB_FILE_BYTES: raise HTTPException(413, "Arquivo excede 10 MB.")
    try:
        ext = extract_job_file_text(content, file.filename or "")
    except (OCRUnavailableError, ValueError) as e:
        raise HTTPException(503 if isinstance(e, OCRUnavailableError) else 422, str(e))
    result = intake_text(JobIntakeRequest(raw_text=ext["text"], source=source, auto_analyze=auto_analyze, reprocess_existing=False), user)
    result["extraction"] = {"method": ext["method"], "filename": ext["filename"], "characters": ext["characters"]}
    return result

@app.post("/intake/file/preview")
async def preview_file(file: UploadFile = File(...), source: str = "print", user=Depends(authenticated_user)):
    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    if len(content) > MAX_JOB_FILE_BYTES: raise HTTPException(413, "Arquivo excede 10 MB.")
    try:
        ext = extract_job_file_text(content, file.filename or "")
        parsed = parse_job_text(ext["text"], source)
    except (OCRUnavailableError, ValueError) as e:
        raise HTTPException(503 if isinstance(e, OCRUnavailableError) else 422, str(e))
    enriched = infer_from_public_url(parsed)
    fetch_error = ""
    if parsed["url"]:
        try:
            structured = await run_in_threadpool(fetch_job_posting, parsed["url"])
        except SourceFetchError as e:
            structured = None; fetch_error = str(e)
        if structured:
            enriched = dict(parsed)
            for f in ("title", "company", "description", "location", "modality", "salary", "url"):
                if structured.get(f): enriched[f] = structured[f]
            enriched["confidence"] = structured["confidence"]; enriched["method"] = structured["method"]
    selected = enriched or dict(parsed)
    confidence = int(selected.get("confidence", 55))
    method = selected.get("method", "local_ocr")
    if confidence >= 85:
        confirmed = await run_in_threadpool(confirm_job_intake, JobIntakeConfirmRequest(external_id=parsed["external_id"], source=parsed["source"], company=selected["company"], title=selected["title"], location=selected["location"], modality=selected["modality"], salary=selected["salary"], url=selected["url"], description=selected["description"], auto_analyze=True), user)
        confirmed.update({"automatic": True, "confidence": confidence, "extraction_method": method})
        return confirmed
    return {"status": "REVISAO_NECESSARIA", "message": "Confianca abaixo do limite.", "external_id": parsed["external_id"], "source": parsed["source"], "company": selected["company"], "title": selected["title"], "location": selected["location"], "modality": selected["modality"], "salary": selected["salary"], "url": selected["url"], "description": selected["description"], "confidence": confidence, "extraction_method": method, "fetch_error": fetch_error, "extraction": {"method": ext["method"], "filename": ext["filename"], "characters": ext["characters"]}}

@app.post("/intake/confirm")
def confirm_intake(req: JobIntakeConfirmRequest, user=Depends(authenticated_user)):
    if not re.fullmatch(r"intake-[0-9a-f]{24}", req.external_id): raise HTTPException(422, "Identificador invalido.")
    if len(req.title.strip()) < 3 or len(req.company.strip()) < 2: raise HTTPException(422, "Confira cargo e empresa.")
    if len(req.description.strip()) < 60: raise HTTPException(422, "Descricao muito curta.")
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        ext_id = f"{oid}:{req.external_id}" if oid else req.external_id
        job = db.scalar(select(Job).where(Job.external_id == ext_id))
        updated = job is not None
        vals = {"source": req.source.strip()[:50], "company": req.company.strip()[:200], "title": req.title.strip()[:200], "location": req.location.strip()[:200], "modality": req.modality.strip()[:50], "salary": req.salary.strip()[:100], "url": req.url.strip()[:1000], "description": req.description.strip()}
        if job is None:
            job = Job(owner_id=oid, external_id=ext_id, **vals); db.add(job); db.flush()
        else:
            for k, v in vals.items(): setattr(job, k, v)
        c = _candidate_for_user(db, user)
        app = _ensure_app(db, job, c)
        quality = assess_job_capture(vals)
        _save_quality(app, quality)
        analysis = None
        if req.auto_analyze:
            arts = _build_application(job, c)
            analysis = arts["analysis"]
            _save_analysis(app, analysis, c)
            if app.status in ("IDENTIFICADA", "ARQUIVADA"):
                _advance_app(db, app, "ANALISADA", "Dados revisados, confirmados e analisados.")
            elif updated:
                db.add(ApplicationEvent(application=app, status=app.status, note="Dados revisados e score recalculado."))
            else:
                _advance_app(db, app, "ANALISADA", "Vaga confirmada e analisada.")
        else:
            _apply_decision(app, c, None)
        db.commit(); db.refresh(job); db.refresh(app)
        return {"status": "VAGA_ATUALIZADA" if updated else "VAGA_CAPTADA", "updated": updated, "job_id": job.id, "application_id": app.id, "application_status": app.status, "company": job.company, "job_title": job.title, "analysis": analysis}
    except: db.rollback(); raise
    finally: db.close()

@app.get("/jobs")
def list_jobs_endpoint(user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        q = select(Job).order_by(Job.id.desc())
        oid = _owner_id(user)
        if oid: q = q.where(Job.owner_id == oid)
        jobs = db.scalars(q).all()
        return {"total": len(jobs), "jobs": [{"id": j.id, "source": j.source, "external_id": j.external_id, "company": j.company, "title": j.title, "location": j.location, "modality": j.modality, "salary": j.salary, "url": j.url} for j in jobs]}
    finally: db.close()

@app.get("/jobs/{job_id}")
def get_job_endpoint(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        return {"id": job.id, "source": job.source, "external_id": job.external_id, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "salary": job.salary, "url": job.url, "description": job.description}
    finally: db.close()

@app.get("/applications")
def list_apps(status: str = None, decision: str = None, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        if status and status not in APPLICATION_STATUSES: raise HTTPException(422, "Status invalido.")
        if decision and decision not in ("AUTOMATICA", "REVISAR", "DESCARTAR"): raise HTTPException(422, "Decisao invalida.")
        q = select(Application).join(Application.job).order_by(Application.updated_at.desc())
        oid = _owner_id(user)
        if oid: q = q.where(Job.owner_id == oid)
        if status: q = q.where(Application.status == status)
        if decision: q = q.where(Application.queue_decision == decision)
        apps = db.scalars(q).all()
        return {"total": len(apps), "applications": [_serialize_app(a) for a in apps]}
    finally: db.close()

@app.get("/applications/{app_id}")
def get_app(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        return _serialize_app(app)
    finally: db.close()

@app.get("/applications/{app_id}/document", response_class=FileResponse)
def download_doc(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        if not app.document_path: raise HTTPException(404, "Nao possui curriculo gerado.")
        path = Path(app.document_path).resolve()
        if not path.is_file(): raise HTTPException(404, "Arquivo nao encontrado.")
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.patch("/applications/{app_id}/status")
def update_app_status(app_id: int, req: ApplicationStatusRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        if app.status != req.status or req.note:
            _add_event(db, app, req.status, req.note)
        db.commit(); db.refresh(app)
        return _serialize_app(app)
    finally: db.close()

@app.post("/jobs/{job_id}/analyze")
def analyze_job_saved(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        analysis = arts["analysis"]
        app = _ensure_app(db, job, c)
        _save_analysis(app, analysis, c)
        _advance_app(db, app, "ANALISADA", "Analise e score calculados.")
        db.commit(); db.refresh(app)
        return {"job_id": job.id, "application_id": app.id, "application_status": app.status, "candidate": arts["profile"]["name"], "company": job.company, "job_title": job.title, "analysis": analysis, "next_action": analysis["next_action"]}
    finally: db.close()

@app.post("/jobs/{job_id}/cover-letter")
def create_cover_letter(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        letter = generate_cover_letter(job_title=job.title, company=job.company, profile=arts["profile"], analysis=arts["analysis"], personalization=arts["personalization"])
        app = _ensure_app(db, job, c)
        _save_analysis(app, arts["analysis"], c)
        app.cover_letter_text = letter
        db.commit(); db.refresh(app)
        return {"job_id": job.id, "application_id": app.id, "company": job.company, "job_title": job.title, "candidate": arts["profile"]["name"], "analysis_score": arts["analysis"]["score"], "personalization_score": arts["personalization"]["personalization_score"], "letter": letter}
    finally: db.close()

@app.post("/jobs/{job_id}/cover-letter/document", response_class=FileResponse)
def create_cover_letter_doc(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        letter = generate_cover_letter(job_title=job.title, company=job.company, profile=arts["profile"], analysis=arts["analysis"], personalization=arts["personalization"])
        path = Path(generate_cover_letter_docx(letter=letter, company=job.company, job_title=job.title)).resolve()
        if not path.is_file(): raise HTTPException(500, "Carta nao foi criada.")
        app = _ensure_app(db, job, c)
        _save_analysis(app, arts["analysis"], c)
        app.cover_letter_text = letter
        app.cover_letter_path = str(path)
        db.add(ApplicationEvent(application_id=app.id, status=app.status, note="Carta de apresentacao gerada."))
        db.commit()
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.get("/applications/{app_id}/cover-letter/document", response_class=FileResponse)
def download_cover_letter(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        if not app.cover_letter_path: raise HTTPException(404, "Nao possui carta gerada.")
        path = Path(app.cover_letter_path).resolve()
        if not path.is_file(): raise HTTPException(404, "Arquivo nao encontrado.")
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.post("/jobs/{job_id}/generate-document", response_class=FileResponse)
def generate_doc(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga não encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        path = Path(generate_docx(arts["resume"])).resolve()
        if not path.is_file(): raise HTTPException(500, "Documento nao foi criado.")
        app = _ensure_app(db, job, c)
        _save_analysis(app, arts["analysis"], c)
        app.personalization_score = arts["personalization"]["personalization_score"]
        app.document_path = str(path)
        _advance_app(db, app, "CURRICULO_GERADO", "Curriculo personalizado gerado.")
        db.commit()
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name, headers={"X-Application-Id": str(app.id), "X-Application-Status": app.status, "X-Analysis-Score": str(arts["analysis"]["score"]), "X-Personalization-Score": str(arts["personalization"]["personalization_score"])})
    finally: db.close()

@app.post("/generate-document")
def generate_doc_standalone(req: ResumeRequest):
    r = req.resume.copy()
    r["target"] = req.title
    path = generate_docx(r)
    return {"status": "DOCUMENTO_GERADO", "candidate": r.get("candidate", {}).get("name", "Candidato"), "job_title": req.title, "file": path}


# Compatibilidade para integrações locais que chamavam os nomes anteriores
# diretamente. Os endpoints públicos continuam sendo os definidos acima.
analyze = analyze_job_endpoint
analyze_saved_job = analyze_job_saved
get_application = get_app
list_applications = list_apps
update_application_status = update_app_status
generate_document_for_job = generate_doc
download_application_document = download_doc
create_cover_letter_for_job = create_cover_letter
create_cover_letter_document = create_cover_letter_doc
download_application_cover_letter = download_cover_letter

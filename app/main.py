import asyncio
import json
import base64
import hashlib
import hmac
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select, text, update
from starlette.concurrency import run_in_threadpool

from .auth import AuthMiddleware, authenticated_user, router as auth_router
from .gmail_integration import router as gmail_router
from .outlook_integration import router as outlook_router
from .outlook_monitor import router as outlook_monitor_router, start_monitor as start_outlook_monitor, stop_monitor as stop_outlook_monitor
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
from .models import Application, ApplicationEvent, Candidate, DocumentExportPurchase, Experience, Job, Skill, utc_now
from .resume_importer import MAX_UPLOAD_BYTES, parse_resume
from .upload_validation import validate_image_upload
from .text_sanitization import sanitize_untrusted_text
from .document_storage import cleanup_expired_documents
from .resume_document import MASTER_PROFILE, generate_docx
from .resume_generator import generate_resume
from .resume_personalizer import personalize_resume
from .queue_service import enqueue
from .ai_provider import AIProviderError, evaluate_interview_answer
from .security import SecurityHeadersMiddleware, current_csp_nonce

app = FastAPI(title="Agente de Candidaturas", version="0.24.0")
logger = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"detail": "Os dados enviados sao invalidos.", "code": "invalid_request"},
        status_code=422,
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Erro interno nao tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": "Nao foi possivel processar a solicitacao agora. Tente novamente em instantes.", "code": "internal_error"},
        status_code=500,
    )


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(gmail_router)
app.include_router(outlook_router)
app.include_router(outlook_monitor_router)
app.include_router(gmail_monitor_router)
app.include_router(queue_router)

APPLICATION_STATUSES = ("IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA")
DOCUMENT_PROCESSING_TIMEOUT = 30


async def _run_document_work(function, *args):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(function, *args),
            timeout=DOCUMENT_PROCESSING_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "O processamento demorou mais que o limite seguro. Tente um arquivo menor ou novamente em instantes.") from exc


async def _run_fetch_work(function, *args):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(function, *args),
            timeout=DOCUMENT_PROCESSING_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise SourceFetchError("A leitura da página excedeu o limite seguro.") from exc
DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"
LANDING_PATH = Path(__file__).parent / "static" / "landing.html"
SETTINGS_PATH = Path(__file__).parent / "static" / "settings.html"
PROFILE_PAGE_PATH = Path(__file__).parent / "static" / "profile.html"
SECURITY_PAGE_PATH = Path(__file__).parent / "static" / "security.html"
ONBOARDING_PATH = Path(__file__).parent / "static" / "onboarding.html"
RESUMES_PATH = Path(__file__).parent / "static" / "curriculos.html"
DOCUMENT_STUDIO_PATH = Path(__file__).parent / "static" / "document-studio.html"
CONFIG_PATH = Path(__file__).parent / "static" / "configuracoes.html"
JOBS_PAGE_PATH = Path(__file__).parent / "static" / "vagas.html"
APPLICATIONS_PAGE_PATH = Path(__file__).parent / "static" / "candidaturas.html"
INTERVIEWS_PAGE_PATH = Path(__file__).parent / "static" / "entrevistas.html"
SIMULATOR_PAGE_PATH = Path(__file__).parent / "static" / "simulador.html"
SIMULATOR_SMART_PATH = Path(__file__).parent / "static" / "simulador-inteligente.html"
TERMS_PATH = Path(__file__).parent / 'static' / 'termos.html'
PRIVACY_PATH = Path(__file__).parent / 'static' / 'privacidade.html'
EMAIL_VERIFICATION_PATH = Path(__file__).parent / 'static' / 'email-verification.html'
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/static/{asset_path:path}", include_in_schema=False)
async def static_asset(asset_path: str):
    """Serve frontend assets without allowing filesystem traversal."""
    candidate = (STATIC_DIR / asset_path).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")
    return FileResponse(candidate)

def _page(path: Path) -> HTMLResponse:
    html = path.read_text(encoding="utf-8")
    if path.name == "settings.html":
        html = html.replace("Integração OAuth em preparação.", "Conecte sua conta Outlook para sincronizar mensagens.")
        html = html.replace(">Em breve<", ">Não conectado<")
        html = html.replace('<span class="badge" style="color:#64748b;background:#f1f5f9">Não conectado</span>', '<span class="badge" style="color:#a15c00;background:#fff5df">Não conectado</span><a class="secondary" href="/auth/outlook/start">Conectar</a>')
    nav = '''<style>.global-nav{height:52px;background:#092f56;color:#fff;display:flex;align-items:center;gap:18px;padding:0 max(22px,5vw);font:600 13px Inter,system-ui,sans-serif}.global-nav a{color:#dcecf8;text-decoration:none}.global-nav a:first-child{color:#fff;font-weight:800;margin-right:auto}.global-nav a:hover{text-decoration:underline}.global-status{color:#b9f1d2;font-size:11px;white-space:nowrap}.breadcrumbs{max-width:1060px;margin:0 auto;padding:16px 18px 0;color:#718198;font-size:12px}.breadcrumbs a{color:#3975a8;text-decoration:none}@media(max-width:650px){.global-nav{gap:10px;padding:0 14px;font-size:12px}.global-nav a:nth-child(n+5){display:none}.global-status{display:none}}</style><nav class="global-nav"><a href="/dashboard">AC · Agente de Candidaturas</a><a href="/vagas">Vagas</a><a href="/candidaturas">Candidaturas</a><a href="/criar-documentos">Criar documentos</a><a href="/entrevistas">Entrevistas</a><a href="/perfil">Perfil</a><a href="/configuracoes">Configurações</a><span class="global-status">● Sistema conectado</span></nav>'''
    nav += '<style>button,.button,.btn,.refresh,.new-job,.action-button,.queue-action{font-family:inherit;min-height:42px}select{min-height:42px;border-radius:10px}.status-success{color:#16794b;background:#eaf8f1}.status-warning{color:#a15c00;background:#fff5df}.status-neutral{color:#596579;background:#eef1f5}.status-danger{color:#b42318;background:#fff0ee}@media(max-width:700px){.wrap{width:calc(100% - 24px);padding-top:24px}.top{padding:12px 14px;min-height:58px}.top nav{flex-wrap:wrap}.card{padding:18px}.actions button,.button{min-height:44px}.queue-panel{overflow:hidden}.queue-panel table{display:block;overflow-x:auto;white-space:nowrap}.queue-panel th:nth-child(3),.queue-panel td:nth-child(3){display:none}}</style>'
    nav += '<style>.back-link{display:inline-flex;align-items:center;gap:5px;margin-right:12px;padding:6px 10px;border:1px solid #dbe6f0;border-radius:8px;color:#315d83!important;background:#fff;font-weight:700}.back-link:hover{background:#f3f8fc;text-decoration:none!important}</style>'
    dashboard_insert = ""
    if path.name == "dashboard.html":
        style_end = nav.rfind("</style>") + len("</style>")
        dashboard_insert = nav[style_end:]
        nav = nav[:style_end]
        nav += '<style>#newJobButton{display:none!important}.hero{display:grid;grid-template-columns:minmax(300px,1fr) auto;align-items:end;gap:32px}.hero h1{max-width:520px;font-size:clamp(32px,3.8vw,44px)}.hero-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;max-width:560px}.hero-actions button{width:auto;white-space:nowrap}@media(max-width:900px){.hero{grid-template-columns:1fr}.hero-actions{justify-content:flex-start;max-width:none}}@media(max-width:700px){main{margin:24px 12px 60px}.metrics{grid-template-columns:1fr}.queue-summary{grid-template-columns:1fr 1fr}.hero{display:block}.hero-actions{margin-top:20px;display:grid;grid-template-columns:1fr 1fr}.hero-actions button{width:100%}.queue-actions{gap:8px}.queue-actions button{min-height:42px;padding:9px 11px}}</style>'
        dashboard_insert += '<script>document.addEventListener("DOMContentLoaded",()=>{const s=document.querySelector("#queueStatusFilter");if(s){s.options[0].text="Status da oportunidade";s.title="Filtra em que ponto da análise a oportunidade está."}const d=document.querySelector("#queueDecisionFilter");if(d)d.title="Decisão sugerida pelo agente: avançar, revisar ou descartar.";const cards=document.querySelectorAll(".metric");if(cards.length>=4){cards[0].querySelector(".metric-label").textContent="Novas vagas para você";cards[1].querySelector(".metric-label").textContent="Compatibilidade média";cards[2].querySelector(".metric-label").textContent="Pendentes de ação";cards[3].querySelector(".metric-label").textContent="Resolvidas"}Promise.all([fetch("/jobs").then(r=>r.json()),fetch("/applications").then(r=>r.json())]).then(([j,a])=>{const apps=a.applications||[],scores=apps.map(x=>Number(x.analysis_score)).filter(Number.isFinite),pending=apps.filter(x=>x.queue_decision==="REVISAR").length,resolved=apps.filter(x=>["APROVADO","RECUSADO","ARQUIVADA"].includes(x.status)).length;if(cards.length>=4){cards[0].querySelector(".metric-value").textContent=(j.jobs||[]).length;cards[0].querySelector(".metric-note").textContent="oportunidades capturadas";cards[1].querySelector(".metric-value").textContent=scores.length?Math.round(scores.reduce((x,y)=>x+y,0)/scores.length)+"%":"—";cards[1].querySelector(".metric-note").textContent="média das vagas analisadas";cards[2].querySelector(".metric-value").textContent=pending;cards[2].querySelector(".metric-note").textContent=pending?"Revisar "+pending+" pendentes":"Nenhuma pendência";cards[3].querySelector(".metric-value").textContent=resolved;cards[3].querySelector(".metric-note").textContent="já processadas"}})}).catch(()=>{})})</script>'
    label = {"vagas.html":"Vagas", "candidaturas.html":"Candidaturas", "curriculos.html":"Currículos", "document-studio.html":"Criar documentos", "simulador-inteligente.html":"Entrevistas", "configuracoes.html":"Configurações", "profile.html":"Perfil", "security.html":"Segurança", "onboarding.html":"Mapeamento"}.get(path.name, "")
    crumb = f'<div class="breadcrumbs"><a class="back-link" href="/dashboard">← Voltar</a><a href="/dashboard">Início</a> <span> / {label}</span></div>' if label else ""
    html = html.replace("<section class=\"hero\">", dashboard_insert + "<section class=\"hero\">", 1)
    extra = '<script src="/static/modal-a11y.js"></script><script src="/static/ui-feedback.js"></script>'
    if path.name == "vagas.html": extra = '<script src="/static/jobs-enhance.js"></script>'
    if path.name == "candidaturas.html": extra = '<script src="/static/applications-enhance.js"></script><script src="/static/applications-transparency.js"></script>'
    if path.name == "onboarding.html": extra = '<script src="/static/onboarding-v2.js"></script>'
    if path.name == "profile.html": extra = '<script src="/static/profile-enhance.js"></script>'
    if path.name == "configuracoes.html": extra = '<script src="/static/preferences-enhance.js"></script>'
    if path.name == "configuracoes.html": extra += '<script src="/static/alerts-enhance.js"></script>'
    if path.name == "configuracoes.html": extra += '<script src="/static/settings-enhance.js?v=1"></script>'
    if path.name == "settings.html": extra += '<script src="/static/settings-enhance.js?v=2"></script>'
    if path.name == "settings.html": extra += '<script src="/static/outlook-enhance.js?v=3"></script>'
    if path.name == "security.html": extra = '<script src="/static/security-enhance.js?v=3"></script>'
    html = html.replace("</body>", extra + "</body>", 1)
    nonce = current_csp_nonce()
    html = re.sub(
        r"<script(?![^>]*\bsrc=)([^>]*)>",
        lambda match: f'<script nonce="{nonce}"{match.group(1)}>',
        html,
        flags=re.I,
    )
    return HTMLResponse(html.replace("<body>", "<body>" + nav + crumb, 1))

def _owner_id(user): return user.get("id") if isinstance(user, dict) else None


def _document_export_price() -> str:
    configured = os.getenv("DOCUMENT_EXPORT_PRICE", "").strip()
    if configured:
        return configured
    raw_cents = os.getenv("DOCUMENT_EXPORT_PRICE_CENTS", "").strip()
    try:
        cents = int(raw_cents)
    except (TypeError, ValueError):
        return ""
    return f"R$ {cents / 100:.2f}".replace(".", ",") if cents > 0 else ""


def _document_export_metadata(user: dict | None) -> dict[str, Any]:
    """Return the server-side entitlement metadata for DOCX exports.

    The payment provider/webhook can grant access through Supabase app_metadata
    (``plan=pro`` or ``document_export_paid=true``).  An email allowlist is
    available for one-off purchases until the checkout integration is wired.
    """
    # Direct calls from internal compatibility helpers/tests do not represent a
    # browser request and keep the historical behavior of returning a file.
    if not isinstance(user, dict):
        return {"allowed": True, "price": _document_export_price(), "checkout_url": os.getenv("DOCUMENT_EXPORT_CHECKOUT_URL", "").strip()}

    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}
    plan = str(app_metadata.get("plan") or app_metadata.get("subscription_plan") or "").strip().casefold()
    paid_flag = app_metadata.get("document_export_paid") or app_metadata.get("document_export_access")
    paid_flag = str(paid_flag).strip().casefold() in {"1", "true", "yes", "paid", "pro"}
    allowed_emails = {
        item.strip().casefold()
        for item in os.getenv("DOCUMENT_EXPORT_ALLOWED_EMAILS", "").split(",")
        if item.strip()
    }
    email = str(user.get("email") or "").strip().casefold()
    local_paid = False
    owner_id = str(user.get("id") or "").strip()
    if owner_id:
        db = SessionLocal()
        try:
            local_paid = db.scalar(
                select(DocumentExportPurchase.id).where(
                    DocumentExportPurchase.owner_id == owner_id,
                    DocumentExportPurchase.status == "PAID",
                ).limit(1)
            ) is not None
        except Exception:
            # Bases antigas podem ainda não ter recebido a tabela nova.
            local_paid = False
        finally:
            db.close()
    allowed = plan in {"pro", "premium", "pro_monthly", "pro_yearly"} or paid_flag or email in allowed_emails or local_paid
    return {
        "allowed": allowed,
        "price": _document_export_price(),
        "checkout_url": os.getenv("DOCUMENT_EXPORT_CHECKOUT_URL", "").strip(),
        "checkout_ready": bool(os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()),
    }


def _require_document_export(user: dict | None) -> dict[str, Any]:
    offer = _document_export_metadata(user)
    if offer["allowed"]:
        return offer
    detail = {
        "code": "DOCUMENT_EXPORT_PAYMENT_REQUIRED",
        "message": "A prévia é gratuita. O download do currículo e da carta exige o plano Pro ou pagamento avulso.",
        "price": offer["price"],
        "checkout_url": offer["checkout_url"],
    }
    raise HTTPException(status_code=402, detail=detail)


def _cover_letter_preview(text_value: str | None, limit: int = 560) -> str:
    """Keep the free preview useful without exposing the complete letter."""
    text_value = str(text_value or "").strip()
    if len(text_value) <= limit:
        return text_value
    cut = text_value[:limit]
    boundary = max(cut.rfind("\n\n"), cut.rfind(". "))
    if boundary >= int(limit * 0.55):
        cut = cut[: boundary + (2 if text_value[boundary:boundary + 2] == ". " else 0)]
    return cut.rstrip() + "…"


def _masked_name(name: str | None) -> str:
    parts = [part for part in str(name or "Candidato").split() if part]
    if len(parts) <= 1:
        return parts[0] if parts else "Candidato"
    return f"{parts[0]} " + " ".join(f"{part[0]}." for part in parts[1:])


def _masked_email(email: str | None) -> str:
    value = str(email or "").strip()
    if "@" not in value:
        return "contato oculto"
    local, domain = value.split("@", 1)
    return f"{local[:1]}•••@•••{domain[domain.rfind('.'):]}" if "." in domain else f"{local[:1]}•••@•••"


def _resume_preview(arts: dict[str, Any]) -> dict[str, Any]:
    resume = arts["resume"]
    summary = str(resume.get("summary") or "")
    candidate = resume.get("candidate") or {}
    contact = candidate
    return {
        "name": _masked_name(candidate.get("name", "Candidato")),
        "target": resume.get("target", ""),
        "headline": resume.get("headline", ""),
        "summary": summary[:420] + ("…" if len(summary) > 420 else ""),
        "skills": list(resume.get("skills") or [])[:8],
        "contact": {
            "email": _masked_email(contact.get("email")),
            "phone": "telefone oculto",
            "location": contact.get("location") or "Localização oculta",
        },
        "experiences": [
            {
                "company": "Empresa confidencial",
                "role": item.get("role", ""),
                "period": item.get("period", ""),
            }
            for item in (resume.get("experiences") or [])[:3]
        ],
        "personalization_score": arts["personalization"].get("personalization_score", 0),
        "notice": "Prévia gratuita. O arquivo completo fica disponível após o plano Pro ou pagamento avulso.",
    }


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
class DocumentStudioRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(default="", max_length=200)
    details: str = Field(min_length=20, max_length=16000)
    location: str = Field(default="", max_length=300)
    url: str = Field(default="", max_length=1000)
class ApplicationStatusRequest(BaseModel): status: Literal["IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"]; note: str = ""
class CandidatePreferencesRequest(BaseModel): target_roles: list[str] = []; locations: list[str] = []; modalities: list[str] = []; contract_types: list[str] = []; schedules: list[str] = []; industries: list[str] = []; excluded_companies: list[str] = []; required_keywords: list[str] = []; excluded_keywords: list[str] = []; salary_min: int | None = None; salary_max: int | None = None; minimum_score: int = 65; automatic_score: int = 85; allow_automatic: bool = False; max_daily_applications: int = 5
class ProfileUpdateRequest(BaseModel): name: str; headline: str = ""; summary: str = ""; location: str = ""; phone: str = ""; linkedin: str = ""; website: str = ""; industry: str = ""; target_roles: list[str] = []; profile_data: dict[str, Any] = Field(default_factory=dict)
class InterviewAnswerRequest(BaseModel): question: str = Field(min_length=3, max_length=500); answer: str = Field(min_length=5, max_length=12000); context: str = Field(default="", max_length=4000)

@app.post("/api/interviews/evaluate")
async def evaluate_interview(req: InterviewAnswerRequest, user=Depends(authenticated_user)):
    try:
        return await evaluate_interview_answer(req.question, req.answer, req.context)
    except AIProviderError as exc:
        logger.warning("Provedor de IA indisponivel na avaliacao de entrevista: %s", exc)
        raise HTTPException(503, "A analise nao esta disponivel agora. Tente novamente em instantes.") from exc

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
def _serialize_app(a, include_document_paths: bool = True, include_cover_letter_text: bool = False):
    an = None
    if a.analysis_data:
        try: an = json.loads(a.analysis_data)
        except: pass
    try: dr = json.loads(a.decision_reasons or "[]")
    except: dr = []
    try: fc = json.loads(a.field_confidence or "{}")
    except: fc = {}
    return {"id": a.id, "job_id": a.job_id, "candidate_id": a.candidate_id, "company": a.job.company, "job_title": a.job.title, "job_url": a.job.url, "status": a.status, "analysis_score": a.analysis_score, "personalization_score": a.personalization_score, "recommendation": a.recommendation, "queue_decision": a.queue_decision or "REVISAR", "decision_reasons": dr, "capture_confidence": a.capture_confidence, "field_confidence": fc, "analysis": an, "document_path": a.document_path if include_document_paths else None, "cover_letter_text": a.cover_letter_text if include_cover_letter_text else _cover_letter_preview(a.cover_letter_text), "cover_letter_path": a.cover_letter_path if include_document_paths else None, "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(), "events": [{"id": e.id, "status": e.status, "note": e.note, "created_at": e.created_at.isoformat()} for e in a.events]}
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
    cleanup_expired_documents()
    start_monitor()
    start_outlook_monitor()

@app.on_event("shutdown")
async def shutdown():
    await stop_monitor()
    await stop_outlook_monitor()

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    if not LANDING_PATH.is_file():
        return {"agente": "Agente de Candidaturas", "status": "online", "version": "0.24.0", "dashboard": "/dashboard"}
    html = LANDING_PATH.read_text(encoding="utf-8")
    auth_script = (Path(__file__).parent / "static" / "landing-auth.js").read_text(encoding="utf-8")
    nonce = current_csp_nonce()
    return HTMLResponse(html.replace("</body>", f'<script src="/static/modal-a11y.js"></script><script src="/static/landing-enhance.js"></script><script nonce="{nonce}">' + auth_script + '</script></body>', 1))

@app.head("/", include_in_schema=False)
def root_head():
    # Alguns monitores fazem HEAD na URL raiz; aproveite o ping para manter o banco ativo.
    health()
    return Response(status_code=200)

@app.get("/termos", response_class=HTMLResponse, include_in_schema=False)
def terms_page():
    return HTMLResponse(TERMS_PATH.read_text(encoding="utf-8"))

@app.get("/privacidade", response_class=HTMLResponse, include_in_schema=False)
def privacy_page():
    return HTMLResponse(PRIVACY_PATH.read_text(encoding="utf-8"))

@app.get("/auth/verification-required", response_class=HTMLResponse, include_in_schema=False)
def email_verification_page():
    if not EMAIL_VERIFICATION_PATH.is_file():
        raise HTTPException(500, "Pagina de confirmacao nao encontrada.")
    return HTMLResponse(EMAIL_VERIFICATION_PATH.read_text(encoding="utf-8"))

@app.get("/health", include_in_schema=False)
def health():
    try:
        # Consulta mínima para confirmar que o processo consegue alcançar o banco.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception:
        logger.exception("Health check do banco falhou")
        # O monitor continua recebendo uma resposta estável sem detalhes internos.
        return {"status": "ok", "db": "error", "detail": "Banco indisponivel."}

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    if not DASHBOARD_PATH.is_file(): raise HTTPException(500, "Dashboard nao encontrado.")
    return _page(DASHBOARD_PATH)

@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page():
    if not SETTINGS_PATH.is_file(): raise HTTPException(500, "Configuracoes nao encontradas.")
    return _page(SETTINGS_PATH)

@app.get("/perfil", response_class=HTMLResponse, include_in_schema=False)
def profile_page():
    if not PROFILE_PAGE_PATH.is_file(): raise HTTPException(500, "Perfil nao encontrado.")
    return _page(PROFILE_PAGE_PATH)

@app.get("/seguranca", response_class=HTMLResponse, include_in_schema=False)
def security_page():
    if not SECURITY_PAGE_PATH.is_file(): raise HTTPException(500, "Seguranca nao encontrada.")
    return _page(SECURITY_PAGE_PATH)

@app.get("/onboarding", response_class=HTMLResponse, include_in_schema=False)
def onboarding_page():
    if not ONBOARDING_PATH.is_file(): raise HTTPException(500, "Onboarding nao encontrado.")
    return _page(ONBOARDING_PATH)

@app.get("/curriculos", response_class=HTMLResponse, include_in_schema=False)
def resumes_page():
    if not RESUMES_PATH.is_file(): raise HTTPException(500, "Curriculos nao encontrados.")
    return _page(RESUMES_PATH)

@app.get("/criar-documentos", response_class=HTMLResponse, include_in_schema=False)
def document_studio_page():
    if not DOCUMENT_STUDIO_PATH.is_file(): raise HTTPException(500, "Criador de documentos nao encontrado.")
    return _page(DOCUMENT_STUDIO_PATH)

@app.get("/configuracoes", response_class=HTMLResponse, include_in_schema=False)
def config_page():
    if not CONFIG_PATH.is_file(): raise HTTPException(500, "Configuracoes nao encontradas.")
    return _page(CONFIG_PATH)

@app.get("/vagas", response_class=HTMLResponse, include_in_schema=False)
def jobs_page():
    if not JOBS_PAGE_PATH.is_file(): raise HTTPException(500, "Vagas nao encontradas.")
    return _page(JOBS_PAGE_PATH)

@app.get("/candidaturas", response_class=HTMLResponse, include_in_schema=False)
def applications_page():
    if not APPLICATIONS_PAGE_PATH.is_file(): raise HTTPException(500, "Candidaturas nao encontradas.")
    return _page(APPLICATIONS_PAGE_PATH)

@app.get("/entrevistas", response_class=HTMLResponse, include_in_schema=False)
def interviews_page():
    if not SIMULATOR_SMART_PATH.is_file(): raise HTTPException(500, "Simulador nao encontrado.")
    return _page(SIMULATOR_SMART_PATH)

@app.get("/simulador", response_class=HTMLResponse, include_in_schema=False)
def simulator_page():
    if not SIMULATOR_SMART_PATH.is_file(): raise HTTPException(500, "Simulador nao encontrado.")
    return _page(SIMULATOR_SMART_PATH)

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
    try:
        filename = Path((file.filename or "foto.png").replace("\\", "/")).name
        content_type = validate_image_upload(content, filename, max_bytes=1_500_000)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
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
    try: parsed = await _run_document_work(parse_resume, content, filename)
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
        safe_title = sanitize_untrusted_text(req.title, max_chars=200)
        safe_description = sanitize_untrusted_text(req.description, max_chars=80_000)
        analysis = analyze_job(f"{safe_title}\n{safe_description}", profile)
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
        for field, limit in (("source", 50), ("company", 200), ("title", 200), ("location", 200), ("modality", 50), ("salary", 100), ("description", 80_000)):
            data[field] = sanitize_untrusted_text(data.get(field, ""), max_chars=limit).strip()
        data["url"] = str(data.get("url") or "").strip()[:1000]
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
            "raw_excerpt": sanitize_untrusted_text(req.raw_text, max_chars=2000),
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
        ext = await _run_document_work(extract_job_file_text, content, file.filename or "")
    except (OCRUnavailableError, ValueError) as e:
        raise HTTPException(503 if isinstance(e, OCRUnavailableError) else 422, str(e))
    result = await _run_document_work(
        intake_text,
        JobIntakeRequest(raw_text=ext["text"], source=source, auto_analyze=auto_analyze, reprocess_existing=False),
        user,
    )
    result["extraction"] = {"method": ext["method"], "filename": ext["filename"], "characters": ext["characters"]}
    return result

@app.post("/intake/file/preview")
async def preview_file(file: UploadFile = File(...), source: str = "print", user=Depends(authenticated_user)):
    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    if len(content) > MAX_JOB_FILE_BYTES: raise HTTPException(413, "Arquivo excede 10 MB.")
    try:
        ext = await _run_document_work(extract_job_file_text, content, file.filename or "")
        parsed = parse_job_text(ext["text"], source)
    except (OCRUnavailableError, ValueError) as e:
        raise HTTPException(503 if isinstance(e, OCRUnavailableError) else 422, str(e))
    enriched = infer_from_public_url(parsed)
    fetch_error = ""
    if parsed["url"]:
        try:
            structured = await _run_fetch_work(fetch_job_posting, parsed["url"])
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
        confirmed = await _run_document_work(
            confirm_job_intake,
            JobIntakeConfirmRequest(external_id=parsed["external_id"], source=parsed["source"], company=selected["company"], title=selected["title"], location=selected["location"], modality=selected["modality"], salary=selected["salary"], url=selected["url"], description=selected["description"], auto_analyze=True),
            user,
        )
        confirmed.update({"automatic": True, "confidence": confidence, "extraction_method": method})
        return confirmed
    return {"status": "REVISAO_NECESSARIA", "message": "Confianca abaixo do limite.", "external_id": parsed["external_id"], "source": parsed["source"], "company": selected["company"], "title": selected["title"], "location": selected["location"], "modality": selected["modality"], "salary": selected["salary"], "url": selected["url"], "description": selected["description"], "confidence": confidence, "extraction_method": method, "fetch_error": fetch_error, "extraction": {"method": ext["method"], "filename": ext["filename"], "characters": ext["characters"]}}

@app.post("/intake/confirm")
def confirm_intake(req: JobIntakeConfirmRequest, user=Depends(authenticated_user)):
    if not re.fullmatch(r"intake-[0-9a-f]{24}", req.external_id): raise HTTPException(422, "Identificador invalido.")
    if len(req.title.strip()) < 3 or len(req.company.strip()) < 2: raise HTTPException(422, "Confira cargo e empresa.")
    safe_description = sanitize_untrusted_text(req.description, max_chars=80_000).strip()
    if len(safe_description) < 60: raise HTTPException(422, "Descricao muito curta.")
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        ext_id = f"{oid}:{req.external_id}" if oid else req.external_id
        job = db.scalar(select(Job).where(Job.external_id == ext_id))
        updated = job is not None
        vals = {"source": sanitize_untrusted_text(req.source, max_chars=50).strip(), "company": sanitize_untrusted_text(req.company, max_chars=200).strip(), "title": sanitize_untrusted_text(req.title, max_chars=200).strip(), "location": sanitize_untrusted_text(req.location, max_chars=200).strip(), "modality": sanitize_untrusted_text(req.modality, max_chars=50).strip(), "salary": sanitize_untrusted_text(req.salary, max_chars=100).strip(), "url": req.url.strip()[:1000], "description": safe_description}
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
        return {"total": len(jobs), "jobs": [{"id": j.id, "source": j.source, "external_id": j.external_id, "company": j.company, "title": j.title, "location": j.location, "modality": j.modality, "salary": j.salary, "url": j.url, "application_id": j.application.id if j.application else None, "application_status": j.application.status if j.application else None, "match_score": getattr(j.application, "analysis_score", None), "captured_at": j.application.created_at.isoformat() if j.application and j.application.created_at else None} for j in jobs]}
    finally: db.close()

@app.get("/jobs/{job_id}")
def get_job_endpoint(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        return {"id": job.id, "source": job.source, "external_id": job.external_id, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "salary": job.salary, "url": job.url, "description": job.description, "application_id": job.application.id if job.application else None, "application_status": job.application.status if job.application else None}
    finally: db.close()

@app.get("/applications")
def list_apps(status: str = None, decision: str = None, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        if status and status not in APPLICATION_STATUSES: raise HTTPException(422, "Status invalido.")
        if decision and decision not in ("AUTOMATICA", "CAPTURAR", "REVISAR", "DESCARTAR"): raise HTTPException(422, "Decisao invalida.")
        q = select(Application).join(Application.job).order_by(Application.updated_at.desc())
        oid = _owner_id(user)
        if oid: q = q.where(Job.owner_id == oid)
        if status: q = q.where(Application.status == status)
        if decision: q = q.where(Application.queue_decision == decision)
        apps = db.scalars(q).all()
        allowed = _document_export_metadata(user)["allowed"]
        return {"total": len(apps), "applications": [_serialize_app(a, allowed, allowed) for a in apps]}
    finally: db.close()

@app.get("/applications/{app_id}")
def get_app(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        allowed = _document_export_metadata(user)["allowed"]
        return _serialize_app(app, allowed, allowed)
    finally: db.close()

@app.get("/billing/document-export")
def document_export_offer(user=Depends(authenticated_user)):
    offer = _document_export_metadata(user)
    return {
        "allowed": offer["allowed"],
        "price": offer["price"],
        "checkout_url": offer["checkout_url"],
        "checkout_ready": offer.get("checkout_ready", False),
        "message": "Download liberado." if offer["allowed"] else "A prévia é gratuita; o download completo exige o plano Pro ou pagamento avulso.",
    }


def _public_base_url() -> str:
    configured = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if configured.startswith("https://"):
        return configured
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    return f"https://{hostname}" if hostname else "https://agente-de-candidaturas.onrender.com"


def _document_export_price_cents() -> int:
    raw = os.getenv("DOCUMENT_EXPORT_PRICE_CENTS", "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(503, "Configure DOCUMENT_EXPORT_PRICE_CENTS no Render.")
    if value < 100:
        raise HTTPException(503, "DOCUMENT_EXPORT_PRICE_CENTS deve ser pelo menos 100 centavos.")
    return value


def _mercadopago_signature_is_valid(request: Request, payload: dict[str, Any]) -> bool:
    """Validate Mercado Pago's HMAC webhook signature before processing it."""
    secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    signature = request.headers.get("x-signature", "").strip()
    request_id = request.headers.get("x-request-id", "").strip()
    payment_id = str(
        (payload.get("data") or {}).get("id")
        or payload.get("id")
        or request.query_params.get("data.id")
        or ""
    ).strip()
    parts = {
        item.split("=", 1)[0].strip(): item.split("=", 1)[1].strip()
        for item in signature.split(",")
        if "=" in item
    }
    timestamp = parts.get("ts", "")
    received = parts.get("v1", "")
    if not secret or not request_id or not payment_id or not timestamp or not received:
        return False
    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - timestamp_int) > 5 * 60:
        return False
    manifest = f"id:{payment_id};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


def _mark_purchase_paid(
    db,
    purchase: DocumentExportPurchase,
    *,
    transaction_nsu: str,
    paid_amount: int,
    invoice_slug: str | None = None,
    receipt_url: str | None = None,
) -> str:
    """Apply one PAID transition and make repeated webhook delivery safe."""
    if purchase.status == "PAID":
        return "idempotent" if purchase.transaction_nsu == transaction_nsu else "conflict"
    values: dict[str, Any] = {
        "status": "PAID",
        "transaction_nsu": transaction_nsu,
        "paid_amount": paid_amount,
        "paid_at": utc_now(),
    }
    if invoice_slug:
        values["invoice_slug"] = invoice_slug
    if receipt_url:
        values["receipt_url"] = receipt_url
    result = db.execute(
        update(DocumentExportPurchase)
        .where(
            DocumentExportPurchase.id == purchase.id,
            DocumentExportPurchase.status != "PAID",
        )
        .values(**values)
    )
    db.commit()
    if result.rowcount == 1:
        return "paid"
    db.refresh(purchase)
    return "idempotent" if purchase.status == "PAID" and purchase.transaction_nsu == transaction_nsu else "conflict"


@app.post("/billing/document-export/checkout")
async def create_document_export_checkout(user=Depends(authenticated_user)):
    owner_id = _owner_id(user)
    if not owner_id:
        raise HTTPException(409, "Login necessário para iniciar o pagamento.")
    mercadopago_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not mercadopago_token:
        raise HTTPException(503, "Checkout Mercado Pago ainda não está configurado.")
    price_cents = _document_export_price_cents()
    order_nsu = f"export-{uuid.uuid4().hex}"
    base_url = _public_base_url()
    payload = {
        "items": [{"id": "document-export", "title": "Exportação de currículo e carta personalizada", "quantity": 1, "currency_id": "BRL", "unit_price": price_cents / 100}],
        "external_reference": order_nsu,
        "payer": {"email": str(user.get("email") or "")},
        "back_urls": {
            "success": f"{base_url}/billing/mercadopago/success",
            "pending": f"{base_url}/billing/mercadopago/success",
            "failure": f"{base_url}/billing/mercadopago/success",
        },
        "auto_return": "approved",
        "notification_url": f"{base_url}/webhooks/mercadopago",
    }
    db = SessionLocal()
    try:
        db.add(DocumentExportPurchase(owner_id=owner_id, order_nsu=order_nsu, amount=price_cents))
        db.commit()
    finally:
        db.close()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.mercadopago.com/checkout/preferences",
                headers={"Authorization": f"Bearer {mercadopago_token}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.exception("Falha ao criar preferência Mercado Pago order_nsu=%s", order_nsu)
        raise HTTPException(502, "Não foi possível criar o checkout Mercado Pago.") from exc
    if response.status_code >= 400:
        logger.warning("Mercado Pago recusou checkout status=%s order_nsu=%s body=%s", response.status_code, order_nsu, response.text[:2000])
        raise HTTPException(502, "O Mercado Pago recusou a criação do checkout.")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, "O Mercado Pago retornou uma resposta inválida.") from exc
    checkout_url = data.get("init_point") or data.get("sandbox_init_point")
    preference_id = str(data.get("id") or "").strip()
    if not checkout_url or not preference_id:
        raise HTTPException(502, "O Mercado Pago não retornou um link de checkout.")
    db = SessionLocal()
    try:
        purchase = db.scalar(select(DocumentExportPurchase).where(DocumentExportPurchase.order_nsu == order_nsu))
        if purchase:
            purchase.invoice_slug = preference_id
            db.commit()
    finally:
        db.close()
    return {"checkout_url": checkout_url, "order_nsu": order_nsu, "provider": "mercadopago"}


@app.post("/webhooks/mercadopago")
async def mercadopago_webhook(request: Request):
    """Verify Mercado Pago payment notifications server-to-server."""
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        return {"received": True, "verified": False}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not _mercadopago_signature_is_valid(request, payload):
        return {"received": True, "verified": False}
    payment_id = str((payload.get("data") or {}).get("id") or payload.get("id") or request.query_params.get("data.id") or "").strip()
    notification_type = str(payload.get("type") or payload.get("topic") or "").strip().casefold()
    if not payment_id or notification_type not in {"payment", "payments", ""}:
        return {"received": True, "verified": False}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError:
        logger.exception("Falha ao consultar pagamento Mercado Pago id=%s", payment_id)
        return {"received": True, "verified": False}
    if response.status_code >= 400:
        logger.warning("Mercado Pago retornou status=%s ao verificar pagamento id=%s", response.status_code, payment_id)
        return {"received": True, "verified": False}
    try:
        payment = response.json()
    except ValueError:
        return {"received": True, "verified": False}
    order_nsu = str(payment.get("external_reference") or "").strip()
    if not order_nsu:
        return {"received": True, "verified": False}
    db = SessionLocal()
    try:
        purchase = db.scalar(select(DocumentExportPurchase).where(DocumentExportPurchase.order_nsu == order_nsu))
        if purchase and str(payment.get("status") or "").casefold() == "approved":
            outcome = _mark_purchase_paid(
                db,
                purchase,
                transaction_nsu=payment_id,
                paid_amount=int(round(float(payment.get("transaction_amount") or 0) * 100)),
            )
            return {"received": True, "verified": outcome != "conflict", "idempotent": outcome == "idempotent", "status": payment.get("status")}
        return {"received": True, "verified": bool(purchase), "status": payment.get("status")}
    finally:
        db.close()


@app.get("/billing/mercadopago/success", response_class=HTMLResponse, include_in_schema=False)
def mercadopago_success():
    return HTMLResponse("<h1>Pagamento recebido</h1><p>Estamos confirmando o pagamento. Volte ao painel para atualizar o acesso ao download.</p><a href='/dashboard'>Voltar ao painel</a>")


@app.get("/applications/{app_id}/document", response_class=FileResponse)
def download_doc(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        _require_document_export(user)
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
        allowed = _document_export_metadata(user)["allowed"]
        return _serialize_app(app, allowed, allowed)
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
        export = _document_export_metadata(user)
        return {"job_id": job.id, "application_id": app.id, "company": job.company, "job_title": job.title, "candidate": arts["profile"]["name"], "analysis_score": arts["analysis"]["score"], "personalization_score": arts["personalization"]["personalization_score"], "letter": letter if export["allowed"] else _cover_letter_preview(letter), "preview": not export["allowed"], "export": export, "notice": "Prévia gratuita. A cópia do texto completo fica disponível após o plano Pro ou pagamento avulso." if not export["allowed"] else "Carta completa liberada."}
    finally: db.close()

@app.post("/jobs/{job_id}/cover-letter/document", response_class=FileResponse)
def create_cover_letter_doc(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        _require_document_export(user)
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
        _require_document_export(user)
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        if not app.cover_letter_path: raise HTTPException(404, "Nao possui carta gerada.")
        path = Path(app.cover_letter_path).resolve()
        if not path.is_file(): raise HTTPException(404, "Arquivo nao encontrado.")
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.post("/jobs/{job_id}/generate-document")
def generate_doc(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga não encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        if not _document_export_metadata(user)["allowed"]:
            app = _ensure_app(db, job, c)
            _save_analysis(app, arts["analysis"], c)
            app.personalization_score = arts["personalization"]["personalization_score"]
            if app.status == "IDENTIFICADA":
                _add_event(db, app, "ANALISADA", "Prévia gratuita gerada; exportação bloqueada.")
            db.commit()
            return {
                "status": "PREVIA_GRATUITA",
                "application_id": app.id,
                "job_id": job.id,
                "company": job.company,
                "job_title": job.title,
                "preview": _resume_preview(arts),
                "export": document_export_offer(user),
            }
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

@app.post("/document-studio/generate")
def generate_document_studio(req: DocumentStudioRequest, user=Depends(authenticated_user)):
    """Create a tailored resume and cover letter from a role pasted by the user.

    The role is saved as a private opportunity so the existing preview, payment,
    export and application tracking flows can be reused consistently.
    """
    db = SessionLocal()
    try:
        candidate = _candidate_for_user(db, user)
        profile = _candidate_profile(candidate)
        title = req.title.strip()
        company = req.company.strip() or "Empresa não informada"
        description = req.details.strip()
        job_data = {
            "source": "studio",
            "external_id": f"{_owner_id(user) or 'local'}:studio:{uuid.uuid4().hex}",
            "company": company,
            "title": title,
            "location": req.location.strip(),
            "modality": "",
            "salary": "",
            "url": req.url.strip(),
            "description": description,
        }
        job = Job(owner_id=_owner_id(user), **job_data)
        db.add(job)
        db.flush()
        app_record = _ensure_app(db, job, candidate)
        arts = _build_application(job, candidate)
        _save_analysis(app_record, arts["analysis"], candidate)
        app_record.personalization_score = arts["personalization"].get("personalization_score", 0)
        app_record.cover_letter_text = generate_cover_letter(
            job_title=title,
            company=company,
            profile=arts["profile"],
            analysis=arts["analysis"],
            personalization=arts["personalization"],
        )
        _advance_app(db, app_record, "ANALISADA", "Documento personalizado criado no Criador de documentos.")
        db.commit()
        db.refresh(job)
        db.refresh(app_record)
        export = _document_export_metadata(user)
        return {
            "status": "PREVIA_GERADA",
            "job_id": job.id,
            "application_id": app_record.id,
            "company": company,
            "job_title": title,
            "analysis": arts["analysis"],
            "resume_preview": _resume_preview(arts),
            "cover_letter_preview": _cover_letter_preview(app_record.cover_letter_text),
            "export": export,
            "notice": "Prévia adaptada ao cargo. O arquivo completo do currículo e da carta fica disponível após o plano Pro ou pagamento avulso.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Falha ao gerar documentos no studio")
        raise HTTPException(500, "Não foi possível gerar os documentos agora.")
    finally:
        db.close()

@app.post("/generate-document")
def generate_doc_standalone(req: ResumeRequest, user=Depends(authenticated_user)):
    _require_document_export(user)
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

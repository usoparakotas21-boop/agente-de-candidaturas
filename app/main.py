import asyncio
import csv
from contextlib import contextmanager
import json
import base64
import hashlib
import hmac
from io import StringIO
import logging
import math
import os
import re
import smtplib
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, quote, urlparse
from weakref import WeakValueDictionary

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, AuthMiddleware, _enforce_rate_limit, authenticated_user, extension_authenticated_user, router as auth_router
from .gmail_integration import router as gmail_router
from .outlook_integration import router as outlook_router
from .outlook_monitor import router as outlook_monitor_router, start_monitor as start_outlook_monitor, stop_monitor as stop_outlook_monitor
from .gmail_monitor import router as gmail_monitor_router, start_monitor, stop_monitor
from .queue_routes import router as queue_router
from .analyzer import analyze_job
from .cover_letter import generate_cover_letter, generate_cover_letter_docx
from .decision_engine import HEURISTICS_VERSION, decide_opportunity, normalize_preferences
from .database import Base, SessionLocal, engine
from .job_intake import parse_job_text
from .job_quality import assess_job_capture
from .job_source_fetcher import SourceFetchError, fetch_job_posting, infer_from_public_url
from .job_file_intake import MAX_JOB_FILE_BYTES, OCRUnavailableError, extract_job_file_text
from .models import Application, ApplicationEvent, BillingSubscription, Candidate, ConsultationCredit, CopilotPreparation, DocumentDelivery, DocumentExportPurchase, EmailApplicationSubmission, EmailIntegration, Experience, ExpiringJobEmailOutbox, FollowupEmailOutbox, GeneratedDocument, InterviewEmailOutbox, Job, JobListing, ProcessedEmailMessage, QueueItem, Skill, utc_now
from .resume_importer import MAX_UPLOAD_BYTES, parse_resume
from .upload_validation import validate_image_upload
from .text_sanitization import sanitize_untrusted_text
from .document_storage import cleanup_expired_documents, resolve_document_path
from .document_pdf import docx_to_pdf
from .data_retention import cleanup_expired_raw_data
from .email_transport import (
    brevo_api_key as _shared_brevo_api_key,
    select_email_transport,
    send_via_brevo_api as _shared_send_via_brevo_api,
)
from .customer_success import FOLLOWUP_POLL_SECONDS, cleanup_followup_email_outbox as cleanup_followup_email_outbox_records, run_followup_digest_cycle, smtp_settings
from .interview_notifications import cleanup_interview_email_outbox, enqueue_interview_notification, run_interview_notification_cycle
from .expiration_notifications import cleanup_expiration_email_outbox, run_expiration_notification_cycle, _parse_preferences as _parse_expiration_preferences
from .resume_document import MASTER_PROFILE, generate_docx
from .resume_generator import generate_resume
from .resume_personalizer import personalize_resume
from .queue_service import enqueue
from .plan_limits import (
    MONTHLY_OPPORTUNITY_LIMITS,
    PlanLimitReachedError,
    ensure_opportunity_capacity,
    month_window,
    monthly_opportunity_usage,
)
from .ai_provider import AIProviderError, evaluate_interview_answer, generate_copilot_suggestions
from .support_chat import router as support_chat_router
from .security import SecurityHeadersMiddleware, current_csp_nonce

app = FastAPI(title="Candidatura Certa", version="0.24.0")
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
app.include_router(support_chat_router)

APPLICATION_STATUSES = ("IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA")
DOCUMENT_PROCESSING_TIMEOUT = 30
MAX_DOCUMENT_EMAIL_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_FILE_BYTES = 10 * 1024 * 1024
DOCUMENT_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PRO_BOOK_PATH = Path(__file__).parent / "private_products" / "hackeando_disc.docx"
DOCUMENT_CLEANUP_INTERVAL_SECONDS = max(
    300,
    int(os.getenv("DOCUMENT_CLEANUP_INTERVAL_SECONDS", str(24 * 60 * 60))),
)
_retention_task: asyncio.Task | None = None
_purchase_generation_task: asyncio.Task | None = None
_purchase_generation_wakeup: asyncio.Event | None = None
_lifecycle_email_task: asyncio.Task | None = None
DOCUMENT_GENERATION_POLL_SECONDS = 15
DOCUMENT_GENERATION_MAX_ATTEMPTS = 5
DOCUMENT_GENERATION_STALE_AFTER = timedelta(minutes=15)
DOCUMENT_GENERATION_BACKOFF_SECONDS = (30, 120, 600, 1800)


def _generated_document_retention_days() -> int:
    try:
        configured = int(os.getenv("DOCUMENT_RETENTION_DAYS", "60"))
    except (TypeError, ValueError):
        configured = 60
    return max(30, min(configured, 3650))


def _cleanup_generated_document_records() -> dict[str, int]:
    """Delete expired document blobs and their related delivery records."""
    db = SessionLocal()
    try:
        if not inspect(db.get_bind()).has_table("generated_documents"):
            return {"documents": 0, "deliveries": 0}
        now = utc_now()
        expired_ids = list(db.scalars(
            select(GeneratedDocument.id).where(GeneratedDocument.expires_at <= now)
        ).all())
        if not expired_ids:
            return {"documents": 0, "deliveries": 0}
        expired_deliveries = db.scalars(
            select(DocumentDelivery).where(
                (DocumentDelivery.resume_document_id.in_(expired_ids))
                | (DocumentDelivery.cover_letter_document_id.in_(expired_ids))
            )
        ).all()
        delivery_ids = [delivery.id for delivery in expired_deliveries]
        document_ids_to_remove = set(expired_ids)
        for delivery in expired_deliveries:
            # A resume and cover letter are one user-facing package; expire both
            # together even if a legacy row has mismatched expiry timestamps.
            document_ids_to_remove.add(delivery.resume_document_id)
            document_ids_to_remove.add(delivery.cover_letter_document_id)
        deliveries_removed = 0
        if delivery_ids:
            deliveries_removed = db.query(DocumentDelivery).filter(
                DocumentDelivery.id.in_(delivery_ids)
            ).delete(synchronize_session=False)
        documents_removed = db.query(GeneratedDocument).filter(
            GeneratedDocument.id.in_(document_ids_to_remove)
        ).delete(synchronize_session=False)
        db.commit()
        return {"documents": int(documents_removed), "deliveries": int(deliveries_removed)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _run_document_work(function, *args):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(function, *args),
            timeout=DOCUMENT_PROCESSING_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "O processamento demorou mais que o limite seguro. Tente um arquivo menor ou novamente em instantes.") from exc


async def _document_retention_loop():
    """Sweep private generated files periodically while the web worker lives."""
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_documents)
            await asyncio.to_thread(_cleanup_generated_document_records)
            await asyncio.to_thread(_cleanup_raw_intake_data)
            await asyncio.to_thread(_cleanup_followup_email_outbox)
            await asyncio.to_thread(_cleanup_interview_email_outbox)
            await asyncio.to_thread(_cleanup_expiration_email_outbox)
            await asyncio.to_thread(_cleanup_copilot_preparations)
            await asyncio.sleep(DOCUMENT_CLEANUP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na limpeza periódica de documentos")
            await asyncio.sleep(DOCUMENT_CLEANUP_INTERVAL_SECONDS)


async def _paid_document_generation_loop():
    """Reconcile the durable one-time export outbox in this web process."""
    while True:
        try:
            await asyncio.to_thread(_process_pending_document_export_purchases, 5)
            event = _purchase_generation_wakeup
            if event is None:
                await asyncio.sleep(DOCUMENT_GENERATION_POLL_SECONDS)
                continue
            try:
                await asyncio.wait_for(event.wait(), timeout=DOCUMENT_GENERATION_POLL_SECONDS)
                event.clear()
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no reconciliador de documentos pagos")
            await asyncio.sleep(DOCUMENT_GENERATION_POLL_SECONDS)


async def _lifecycle_email_loop():
    """Dispatch durable, opt-in interview and follow-up emails."""
    while True:
        try:
            for dispatcher, label in (
                (run_followup_digest_cycle, "lembretes de candidatura"),
                (run_interview_notification_cycle, "avisos de entrevista"),
                (run_expiration_notification_cycle, "avisos de expiração de vagas"),
            ):
                try:
                    await asyncio.to_thread(dispatcher, SessionLocal)
                except Exception:
                    logger.exception("Falha no reconciliador de %s", label)
            await asyncio.sleep(FOLLOWUP_POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no loop de e-mails de ciclo de vida")
            await asyncio.sleep(FOLLOWUP_POLL_SECONDS)


def _cleanup_raw_intake_data() -> dict[str, int]:
    db = SessionLocal()
    try:
        return cleanup_expired_raw_data(db)
    finally:
        db.close()


def _cleanup_followup_email_outbox() -> int:
    db = SessionLocal()
    try:
        return cleanup_followup_email_outbox_records(db)
    finally:
        db.close()


def _cleanup_interview_email_outbox() -> int:
    db = SessionLocal()
    try:
        return cleanup_interview_email_outbox(db)
    finally:
        db.close()


def _cleanup_copilot_preparations() -> int:
    """Remove the extension's minimal usage/audit records after 60 days."""
    db = SessionLocal()
    try:
        cutoff = utc_now() - timedelta(days=60)
        deleted = db.query(CopilotPreparation).filter(CopilotPreparation.created_at < cutoff).delete(synchronize_session=False)
        db.commit()
        return int(deleted or 0)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _start_purchase_generation_worker() -> None:
    global _purchase_generation_task, _purchase_generation_wakeup
    if _purchase_generation_task is None or _purchase_generation_task.done():
        _purchase_generation_wakeup = asyncio.Event()
        _purchase_generation_task = asyncio.create_task(_paid_document_generation_loop())


def _start_lifecycle_email_worker() -> None:
    global _lifecycle_email_task
    if _lifecycle_email_task is None or _lifecycle_email_task.done():
        _lifecycle_email_task = asyncio.create_task(_lifecycle_email_loop())


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
HELP_PAGE_PATH = Path(__file__).parent / "static" / "ajuda.html"
TERMS_PATH = Path(__file__).parent / 'static' / 'termos.html'
PRIVACY_PATH = Path(__file__).parent / 'static' / 'privacidade.html'
EMAIL_VERIFICATION_PATH = Path(__file__).parent / 'static' / 'email-verification.html'
STATIC_DIR = Path(__file__).parent / "static"
FAVICON_TAG = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg?v=2">'


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


def _nonce_styles(html: str, nonce: str) -> str:
    """Attach the response nonce to inline style elements in a template."""
    return re.sub(
        r"<style(?![^>]*\bnonce=)([^>]*)>",
        lambda match: f'<style nonce="{nonce}"{match.group(1)}>',
        html,
        flags=re.I,
    )


def _with_favicon(html: str) -> str:
    """Attach the product favicon to every active HTML shell."""
    if 'rel="icon"' in html.casefold():
        return html
    return html.replace("</head>", FAVICON_TAG + "</head>", 1)


def _landing_demo_video() -> str:
    """Render a responsive demo only for a validated YouTube/Vimeo URL."""
    raw_url = os.getenv("DEMO_VIDEO_URL", "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    video_id = ""
    embed_url = ""
    if parsed.scheme == "https" and host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.removeprefix("/embed/").split("/", 1)[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif parsed.scheme == "https" and host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif parsed.scheme == "https" and host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if host == "player.vimeo.com" and len(parts) >= 2 and parts[-2] == "video":
            video_id = parts[-1]
        else:
            video_id = next((part for part in parts if re.fullmatch(r"[0-9]{5,15}", part)), "")
        if re.fullmatch(r"[0-9]{5,15}", video_id):
            embed_url = f"https://player.vimeo.com/video/{video_id}"
            private_hash = parse_qs(parsed.query).get("h", [""])[0]
            if not private_hash and video_id in parts:
                id_position = parts.index(video_id)
                if len(parts) > id_position + 1 and re.fullmatch(r"[A-Za-z0-9]{1,80}", parts[id_position + 1]):
                    private_hash = parts[id_position + 1]
            if private_hash and re.fullmatch(r"[A-Za-z0-9]{1,80}", private_hash):
                embed_url += f"?h={private_hash}"
    if not embed_url:
        logger.warning("DEMO_VIDEO_URL is not a supported YouTube or Vimeo URL; demo remains hidden")
        return ""
    return f'''<section class="section demo-video-section" id="demonstracao" aria-labelledby="demo-video-title"><div class="section-head"><h2 id="demo-video-title">Veja a Candidatura Certa em ação</h2><p>Da importação do currículo à análise de compatibilidade, documentos e fila de decisão.</p></div><div class="demo-video-frame"><iframe src="{embed_url}" title="Demonstração da Candidatura Certa" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div></section>'''


def _style_nonce_bootstrap(nonce: str) -> str:
    """Allow trusted external enhancements to create nonce-bearing styles."""
    return (
        f'<meta name="csp-nonce" content="{nonce}">'
        f'<script nonce="{nonce}">'
        '(function(){const n=document.querySelector(\'meta[name="csp-nonce"]\')?.content;'
        'if(!n)return;const c=document.createElement.bind(document);'
        'document.createElement=function(t){const e=c(t);if(String(t).toLowerCase()==="style")e.nonce=n;return e;};})();'
        '</script>'
    )


def _page(path: Path) -> HTMLResponse:
    html = path.read_text(encoding="utf-8")
    html = _with_favicon(html)
    html = html.replace("</body>", '<script src="/static/support-chat.js?v=6" defer></script></body>', 1)
    if path.name == "settings.html":
        html = html.replace("Integração OAuth em preparação.", "Conecte sua conta Outlook para sincronizar mensagens.")
        html = html.replace(">Em breve<", ">Não conectado<")
        html = html.replace('<span class="badge" style="color:#64748b;background:#f1f5f9">Não conectado</span>', '<span class="badge" style="color:#a15c00;background:#fff5df">Não conectado</span><a class="secondary" href="/auth/outlook/start">Conectar</a>')
    nav = '''<style>
.global-nav{height:52px;background:#092f56;color:#fff;display:flex;align-items:center;gap:18px;padding:0 max(22px,5vw);font:600 13px Inter,system-ui,sans-serif}
body{min-height:100vh;display:flex;flex-direction:column}
.global-nav a{color:#dcecf8;text-decoration:none}
.global-nav a:first-child{color:#fff;font-weight:800;margin-right:auto}
.global-brand{display:inline-flex;align-items:center;gap:8px}
.global-brand-icon{width:28px;height:28px;display:block;border-radius:50%}
.global-nav a:hover{text-decoration:underline}
.global-status{display:inline-flex;align-items:center;gap:6px;color:#b9f1d2;font-size:11px;white-space:nowrap}
.global-status::before{content:"";width:7px;height:7px;border-radius:50%;background:#58d68d;transform-origin:center;animation:global-online-pulse 1.6s ease-in-out infinite}
.global-logout{margin:0}
.global-logout button{padding:6px 10px;border:1px solid #ffffff55;border-radius:8px;color:#fff;background:transparent;font:inherit;font-size:11px;cursor:pointer}
.global-logout button:hover{background:#ffffff18}
.global-footer{max-width:1160px;margin:auto auto 0;padding:18px 22px calc(96px + env(safe-area-inset-bottom,0px));border-top:1px solid #dce5f1;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;color:#718198;font:12px Inter,system-ui,sans-serif}
.global-footer a{color:#3975a8;text-decoration:none}
.global-footer a:hover{text-decoration:underline}
.global-footer-status{display:inline-flex;align-items:center;gap:7px}
.global-footer-status::before{content:"";width:7px;height:7px;border-radius:50%;background:#a8b3c2}
.global-footer-status[data-state="ok"]::before{background:#28a36a}
.global-footer-status[data-state="error"]::before{background:#d79019}
.breadcrumbs{max-width:1060px;margin:0 auto;padding:16px 18px 0;color:#718198;font-size:12px}
.breadcrumbs a{color:#3975a8;text-decoration:none}
@keyframes global-online-pulse{0%,100%{opacity:1;transform:scale(1);box-shadow:0 0 0 0 rgba(88,214,141,.42)}50%{opacity:.62;transform:scale(.78);box-shadow:0 0 0 5px rgba(88,214,141,0)}}
@media(prefers-reduced-motion:reduce){.global-status::before{animation:none}}
@media(max-width:650px){.global-nav{gap:10px;padding:0 14px;font-size:12px}.global-nav a:nth-child(n+5){display:none}.global-status{display:none}.global-logout button{padding:5px 7px}}
</style>
<nav class="global-nav"><a class="global-brand" href="/dashboard"><img class="global-brand-icon" src="/static/favicon.svg?v=2" alt="" aria-hidden="true"><span>Candidatura Certa</span></a><a href="/vagas">Vagas</a><a href="/candidaturas">Candidaturas</a><a href="/criar-documentos">Criar documentos</a><a href="/entrevistas">Entrevistas</a><a href="/perfil">Perfil</a><a href="/configuracoes">Configurações</a><span class="global-status">Sistema conectado</span><form class="global-logout" method="post" action="/auth/logout"><button type="submit">Sair</button></form></nav>'''
    if path.name == "dashboard.html":
        # O dashboard já possui cabeçalho próprio e navegação lateral.
        # Mantemos apenas os estilos compartilhados para evitar duas barras no topo.
        nav = re.sub(r'<nav class="global-nav">.*?</nav>', "", nav, count=1, flags=re.S)
    nav += '<style>button,.button,.btn,.refresh,.new-job,.action-button,.queue-action{font-family:inherit;min-height:42px}select{min-height:42px;border-radius:10px}.status-success{color:#16794b;background:#eaf8f1}.status-warning{color:#a15c00;background:#fff5df}.status-neutral{color:#596579;background:#eef1f5}.status-danger{color:#b42318;background:#fff0ee}@media(max-width:700px){.wrap{width:calc(100% - 24px);padding-top:24px}.top{padding:12px 14px;min-height:58px}.top nav{flex-wrap:wrap}.card{padding:18px}.actions button,.button{min-height:44px}.queue-panel{overflow:hidden}.queue-panel table{display:block;overflow-x:auto;white-space:nowrap}.queue-panel th:nth-child(3),.queue-panel td:nth-child(3){display:none}}</style>'
    nav += '<style>.back-link{display:inline-flex;align-items:center;gap:5px;margin-right:12px;padding:6px 10px;border:1px solid #dbe6f0;border-radius:8px;color:#315d83!important;background:#fff;font-weight:700}.back-link:hover{background:#f3f8fc;text-decoration:none!important}</style>'
    dashboard_insert = ""
    if path.name == "dashboard.html":
        style_end = nav.rfind("</style>") + len("</style>")
        dashboard_insert = nav[style_end:]
        nav = nav[:style_end]
        nav += '<style>#newJobButton{display:none!important}.hero{display:grid;grid-template-columns:minmax(300px,1fr) auto;align-items:end;gap:32px}.hero h1{max-width:520px;font-size:clamp(32px,3.8vw,44px)}.hero-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;max-width:560px}.hero-actions button{width:auto;white-space:nowrap}@media(max-width:900px){.hero{grid-template-columns:1fr}.hero-actions{justify-content:flex-start;max-width:none}}@media(max-width:700px){main{margin:24px 12px 60px}.metrics{grid-template-columns:1fr}.queue-summary{grid-template-columns:1fr 1fr}.hero{display:block}.hero-actions{margin-top:20px;display:grid;grid-template-columns:1fr 1fr}.hero-actions button{width:100%}.queue-actions{gap:8px}.queue-actions button{min-height:42px;padding:9px 11px}}</style>'
        dashboard_insert += '<script>document.addEventListener("DOMContentLoaded",()=>{const s=document.querySelector("#queueStatusFilter");if(s){s.options[0].text="Status da oportunidade";s.title="Filtra em que ponto da análise a oportunidade está."}const d=document.querySelector("#queueDecisionFilter");if(d)d.title="Decisão sugerida pelo agente: avançar, revisar ou descartar.";const cards=document.querySelectorAll(".metric");if(cards.length>=4){cards[0].querySelector(".metric-label").textContent="Novas vagas para você";cards[1].querySelector(".metric-label").textContent="Compatibilidade média";cards[2].querySelector(".metric-label").textContent="Pendentes de ação";cards[3].querySelector(".metric-label").textContent="Resolvidas"}Promise.all([fetch("/jobs").then(r=>r.json()),fetch("/applications").then(r=>r.json())]).then(([j,a])=>{const apps=a.applications||[],scores=apps.map(x=>Number(x.analysis_score)).filter(Number.isFinite),pending=apps.filter(x=>x.queue_decision==="REVISAR").length,resolved=apps.filter(x=>["APROVADO","RECUSADO","ARQUIVADA"].includes(x.status)).length;if(cards.length>=4){cards[0].querySelector(".metric-value").textContent=(j.jobs||[]).length;cards[0].querySelector(".metric-note").textContent="oportunidades capturadas";cards[1].querySelector(".metric-value").textContent=scores.length?Math.round(scores.reduce((x,y)=>x+y,0)/scores.length)+"%":"—";cards[1].querySelector(".metric-note").textContent="média das vagas analisadas";cards[2].querySelector(".metric-value").textContent=pending;cards[2].querySelector(".metric-note").textContent=pending?"Revisar "+pending+" pendentes":"Nenhuma pendência";cards[3].querySelector(".metric-value").textContent=resolved;cards[3].querySelector(".metric-note").textContent="já processadas"}})}).catch(()=>{})})</script>'
    label = {"vagas.html":"Vagas", "candidaturas.html":"Candidaturas", "curriculos.html":"Currículos", "document-studio.html":"Criar documentos", "simulador-inteligente.html":"Entrevistas", "configuracoes.html":"Configurações", "profile.html":"Perfil", "security.html":"Segurança", "onboarding.html":"Mapeamento", "ajuda.html":"Ajuda"}.get(path.name, "")
    crumb = f'<div class="breadcrumbs"><a class="back-link" href="/dashboard">← Voltar</a><a href="/dashboard">Início</a> <span> / {label}</span></div>' if label else ""
    html = html.replace("<section class=\"hero\">", dashboard_insert + "<section class=\"hero\">", 1)
    extra = '<script src="/static/modal-a11y.js"></script><script src="/static/ui-feedback.js"></script>'
    if path.name == "vagas.html": extra = '<script src="/static/jobs-enhance.js?v=2"></script>'
    if path.name == "candidaturas.html": extra = '<script src="/static/applications-enhance.js"></script><script src="/static/applications-transparency.js"></script>'
    if path.name == "onboarding.html": extra = '<script src="/static/onboarding-v2.js"></script>'
    if path.name == "profile.html": extra = '<script src="/static/profile-enhance.js"></script><script src="/static/profile-autofill-export.js?v=7"></script>'
    if path.name == "configuracoes.html": extra = '<script src="/static/preferences-enhance.js"></script>'
    if path.name == "configuracoes.html": extra += '<script src="/static/alerts-enhance.js"></script>'
    if path.name == "configuracoes.html": extra += '<script src="/static/settings-enhance.js?v=1"></script>'
    if path.name == "settings.html": extra += '<script src="/static/settings-enhance.js?v=2"></script>'
    if path.name == "settings.html": extra += '<script src="/static/outlook-enhance.js?v=3"></script>'
    if path.name == "security.html": extra = '<script src="/static/security-enhance.js?v=7"></script>'
    nonce = current_csp_nonce()
    html = _nonce_styles(html, nonce)
    footer = '''<footer class="global-footer"><span>© 2026 Candidatura Certa</span><span class="global-footer-status" id="globalServiceStatus" data-state="loading" role="status" aria-live="polite">Verificando sistema…</span><span><a href="/termos">Termos</a> · <a href="/privacidade">Privacidade</a> · <a href="mailto:contato@candidaturacerta.com.br">Suporte</a></span></footer><script>(function(){const el=document.getElementById("globalServiceStatus");if(!el)return;fetch("/health",{credentials:"same-origin"}).then(async r=>{const d=await r.json();if(!r.ok||d.db!=="connected")throw new Error("unavailable");el.textContent="Sistema operacional";el.dataset.state="ok"}).catch(()=>{el.textContent="Sistema temporariamente indisponível";el.dataset.state="error"})})();</script>'''
    html = html.replace("</body>", footer + extra + "</body>", 1)
    html = re.sub(
        r"<script(?![^>]*\bsrc=)([^>]*)>",
        lambda match: f'<script nonce="{nonce}"{match.group(1)}>',
        html,
        flags=re.I,
    )
    rendered = html.replace("<body>", "<body>" + _style_nonce_bootstrap(nonce) + nav + crumb, 1)
    rendered = _nonce_styles(rendered, nonce)
    return HTMLResponse(rendered)

def _owner_id(user): return user.get("id") if isinstance(user, dict) else None


def _job_deadline_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    # SQLite returns timezone-aware DateTime values as naive; these were
    # normalized to UTC when extracted from Schema.org metadata.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


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


SUBSCRIPTION_PLANS: dict[str, dict[str, Any]] = {
    "start": {"name": "Start", "amount": 3490, "monthly_opportunities": MONTHLY_OPPORTUNITY_LIMITS["start"]},
    "pro": {"name": "Pro", "amount": 9900, "monthly_opportunities": MONTHLY_OPPORTUNITY_LIMITS["pro"]},
    "consultoria": {"name": "Consultoria", "amount": 19700},
}
CONSULTATION_WHATSAPP_NUMBER = re.sub(
    r"\D", "", os.getenv("CONSULTATION_WHATSAPP_NUMBER", "5571993494443")
)
_SUBSCRIPTION_CHECKOUT_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _subscription_checkout_lock(owner_id: str) -> asyncio.Lock:
    lock = _SUBSCRIPTION_CHECKOUT_LOCKS.get(owner_id)
    if lock is None:
        lock = asyncio.Lock()
        _SUBSCRIPTION_CHECKOUT_LOCKS[owner_id] = lock
    return lock


def _subscription_access_until(subscription: BillingSubscription | None) -> datetime | None:
    if subscription is None:
        return None
    status = str(subscription.status or "").casefold()
    if status in {"authorized", "paused", "canceled"}:
        return subscription.access_until
    return None


def _subscription_is_entitled(subscription: BillingSubscription | None) -> bool:
    access_until = _subscription_access_until(subscription)
    if subscription is None or access_until is None:
        return False
    now = utc_now()
    # SQLite may return a naive datetime even when timezone=True.
    if access_until.tzinfo is None:
        access_until = access_until.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    # A provider authorization is not proof of a paid period. Entitlement
    # always ends at the latest confirmed access_until timestamp.
    return access_until > now


def _mp_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _monthly_recurring_matches(value: Any, expected_amount: int) -> bool:
    recurring = value if isinstance(value, dict) else {}
    try:
        amount = int(round(float(recurring.get("transaction_amount") or 0) * 100))
        frequency = int(recurring.get("frequency") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        amount == int(expected_amount)
        and str(recurring.get("currency_id") or "").upper() == "BRL"
        and frequency == 1
        and str(recurring.get("frequency_type") or "").casefold() == "months"
    )


def _ensure_consultation_credit(
    db,
    subscription: BillingSubscription,
    payment_id: str,
    period_start: datetime,
    period_end: datetime,
) -> ConsultationCredit | None:
    """Create at most one monthly consultation credit for a verified payment."""
    if subscription.plan_code != "consultoria" or not payment_id or period_end <= period_start:
        return None
    existing = db.scalar(
        select(ConsultationCredit).where(ConsultationCredit.payment_id == payment_id)
    )
    if existing is not None:
        return existing
    credit = ConsultationCredit(
        subscription_id=subscription.id,
        owner_id=subscription.owner_id,
        payment_id=payment_id,
        period_start=period_start,
        period_end=period_end,
        booking_status="available",
    )
    try:
        # A unique payment id makes webhook retries and concurrent delivery safe.
        with db.begin_nested():
            db.add(credit)
            db.flush()
    except IntegrityError:
        return db.scalar(
            select(ConsultationCredit).where(ConsultationCredit.payment_id == payment_id)
        )
    return credit


def _consultation_whatsapp_url(reference: str, availability: str = "") -> str:
    message = (
        "Olá! Quero agendar o atendimento mensal da minha Consultoria Candidatura Certa. "
        f"Código do atendimento: {reference}."
    )
    if availability:
        message += f" Minha disponibilidade: {availability}"
    return f"https://wa.me/{CONSULTATION_WHATSAPP_NUMBER}?text={quote(message, safe='')}"


def _is_valid_mercadopago_checkout_url(value: Any) -> bool:
    try:
        target = httpx.URL(str(value or "").strip())
    except (TypeError, ValueError, httpx.InvalidURL):
        return False
    return target.scheme == "https" and target.host in {"mercadopago.com.br", "www.mercadopago.com.br"}


def _sync_subscription_from_provider(db, provider: dict[str, Any]) -> BillingSubscription | None:
    external_reference = str(provider.get("external_reference") or "").strip()
    provider_id = str(provider.get("id") or "").strip()
    if not external_reference or not provider_id:
        return None
    subscription = db.scalar(
        select(BillingSubscription).where(
            BillingSubscription.external_reference == external_reference
        )
    )
    if subscription is None or subscription.mercadopago_preapproval_id != provider_id:
        return None
    recurring = provider.get("auto_recurring") if isinstance(provider.get("auto_recurring"), dict) else {}
    expected_plan = SUBSCRIPTION_PLANS.get(subscription.plan_code)
    valid_recurring = (
        expected_plan is not None
        and subscription.monthly_amount == expected_plan["amount"]
        and _monthly_recurring_matches(recurring, expected_plan["amount"])
    )
    if not valid_recurring:
        logger.warning(
            "Assinatura Mercado Pago diverge do plano local external_reference=%s",
            external_reference,
        )
        return None
    status = str(provider.get("status") or "").strip().casefold()
    if status == "cancelled":
        status = "canceled"
    if status not in {"authorized", "pending", "paused", "canceled", "rejected"}:
        return None
    next_payment_at = _mp_datetime(provider.get("next_payment_date"))
    subscription.status = status
    if next_payment_at is not None:
        subscription.next_payment_at = next_payment_at
    subscription.updated_at = utc_now()
    db.commit()
    db.refresh(subscription)
    return subscription


def _document_export_metadata(user: dict | None, application_id: int | None = None) -> dict[str, Any]:
    """Return the server-side entitlement metadata for DOCX exports.

    Active local subscriptions are authoritative and time-bounded. Legacy
    app_metadata grants are honored only for accounts with no local subscription.
    """
    # Direct calls from internal compatibility helpers/tests do not represent a
    # browser request and keep the historical behavior of returning a file.
    if not isinstance(user, dict):
        return {"allowed": True, "price": _document_export_price(), "checkout_url": ""}

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
    local_subscription = None
    owner_id = str(user.get("id") or "").strip()
    if owner_id:
        db = SessionLocal()
        try:
            local_paid = db.scalar(
                select(DocumentExportPurchase.id).where(
                    DocumentExportPurchase.owner_id == owner_id,
                    DocumentExportPurchase.status == "PAID",
                    *([DocumentExportPurchase.application_id == application_id] if application_id is not None else []),
                ).limit(1)
            ) is not None
            local_subscription = db.scalar(
                select(BillingSubscription)
                .where(BillingSubscription.owner_id == owner_id)
                .order_by(BillingSubscription.updated_at.desc())
                .limit(1)
            )
        except Exception:
            # Bases antigas podem ainda não ter recebido a tabela nova.
            local_paid = False
            local_subscription = None
        finally:
            db.close()
    local_plan = (
        str(local_subscription.plan_code or "").casefold()
        if _subscription_is_entitled(local_subscription)
        else ""
    )
    legacy_plan_access = plan in {"pro", "premium", "pro_monthly", "pro_yearly"} and local_subscription is None
    allowed = legacy_plan_access or local_plan in {"start", "pro"} or paid_flag or email in allowed_emails or local_paid
    return {
        "allowed": allowed,
        "price": _document_export_price(),
        "checkout_url": "",
        "checkout_ready": bool(os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()),
        "plan": local_plan or ("pro" if legacy_plan_access else "essential"),
    }


def _require_document_export(user: dict | None, application_id: int | None = None) -> dict[str, Any]:
    offer = _document_export_metadata(user, application_id)
    if offer["allowed"]:
        return offer
    detail = {
        "code": "DOCUMENT_EXPORT_PAYMENT_REQUIRED",
        "message": "A prévia é gratuita. O download completo está incluído no Start e no Pro, ou pode ser comprado à parte.",
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
        "notice": "Prévia gratuita. O arquivo completo está incluído no Start e no Pro, ou pode ser comprado à parte.",
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
class JobCreateRequest(BaseModel):
    source: str = "manual"
    external_id: str
    company: str
    title: str
    location: str = ""
    modality: str = ""
    contract_type: str = ""
    modality_confidence: int | None = Field(default=None, ge=0, le=100)
    salary_confidence: int | None = Field(default=None, ge=0, le=100)
    contract_confidence: int | None = Field(default=None, ge=0, le=100)
    salary: str = ""
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    valid_through: datetime | None = None
    url: str = ""
    description: str
class JobIntakeRequest(BaseModel): raw_text: str; source: str = "texto"; auto_analyze: bool = True; reprocess_existing: bool = False
class JobIntakeConfirmRequest(BaseModel):
    external_id: str
    source: str = "print"
    company: str
    title: str
    location: str = ""
    modality: str = ""
    contract_type: str = ""
    modality_confidence: int | None = Field(default=None, ge=0, le=100)
    salary_confidence: int | None = Field(default=None, ge=0, le=100)
    contract_confidence: int | None = Field(default=None, ge=0, le=100)
    salary: str = ""
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    valid_through: datetime | None = None
    url: str = ""
    description: str
    auto_analyze: bool = True
class ResumeRequest(BaseModel): title: str; resume: dict
class DocumentExportCheckoutRequest(BaseModel): application_id: int = Field(gt=0)
class SubscriptionCheckoutRequest(BaseModel): plan_code: Literal["start", "pro", "consultoria"]
class ConsultationBookingRequest(BaseModel): availability: str = Field(min_length=5, max_length=800)
class DocumentStudioExportRequest(BaseModel): application_id: int = Field(gt=0)
class EmailApplicationSubmissionRequest(BaseModel):
    recipient: str = Field(min_length=5, max_length=320)
    body: str = Field(min_length=20, max_length=12000)
    resume_version: str = Field(min_length=3, max_length=32)
    cover_letter_version: str = Field(min_length=3, max_length=32)
    consent: bool = False
class DocumentStudioRequest(BaseModel):
    application_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(default="", max_length=200)
    details: str = Field(min_length=20, max_length=16000)
    location: str = Field(default="", max_length=300)
    url: str = Field(default="", max_length=1000)
class ApplicationStatusRequest(BaseModel):
    status: Literal["IDENTIFICADA", "ANALISADA", "PERSONALIZADA", "CURRICULO_GERADO", "CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"]
    note: str = Field(default="", max_length=2000)
    channel: Literal["", "manual", "gmail", "linkedin", "gupy", "indeed", "site_empresa", "indicacao", "outro"] = ""
    external_result: Literal["", "SEM_RETORNO", "CONTATO_RECRUTADOR", "ENTREVISTA", "RECUSADO", "PROPOSTA"] = ""
class CandidatePreferencesRequest(BaseModel): target_roles: list[str] = []; locations: list[str] = []; modalities: list[str] = []; contract_types: list[str] = []; schedules: list[str] = []; industries: list[str] = []; excluded_companies: list[str] = []; required_keywords: list[str] = []; excluded_keywords: list[str] = []; salary_min: int | None = None; salary_max: int | None = None; minimum_score: int = 65; automatic_score: int = 85; allow_automatic: bool = False; max_daily_applications: int = 5; notification_frequency: Literal["daily", "immediate", "weekly", "none"] = "daily"; notify_interviews: bool = False; notify_interviews_consent: bool = False; notify_expiring: bool = False; notify_expiring_consent: bool = False; notify_followups: bool = False
class ProfileUpdateRequest(BaseModel): name: str; headline: str = ""; summary: str = ""; location: str = ""; phone: str = ""; linkedin: str = ""; website: str = ""; industry: str = ""; target_roles: list[str] = []; profile_data: dict[str, Any] = Field(default_factory=dict)
class CopilotPrepareRequest(BaseModel):
    request_id: str = Field(min_length=36, max_length=36)
    portal_host: str = Field(min_length=3, max_length=255)
    portal_allowed: bool = False
    analysis_only: bool = False
    consent_data_processing: bool = False
    consent_gemini_processing: bool = False
    job_title: str = Field(default="", max_length=200)
    job_company: str = Field(default="", max_length=200)
    job_location: str = Field(default="", max_length=200)
    job_description: str = Field(default="", max_length=12000)

class CopilotCompleteRequest(BaseModel):
    request_id: str = Field(min_length=36, max_length=36)
    filled_count: int = Field(ge=0, le=100)
class ProfileExperienceRequest(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=50)
    end_date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=5000)

class ProfileEducationRequest(BaseModel):
    course: str = Field(min_length=1, max_length=200)
    institution: str = Field(default="", max_length=200)
    period: str = Field(default="", max_length=100)

PROFILE_EXTRACTED_SECTIONS = frozenset({"experiences", "skills", "education", "languages"})

class ExtractedProfileUpdateRequest(BaseModel):
    experiences: list[ProfileExperienceRequest] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=100)
    education: list[ProfileEducationRequest] = Field(default_factory=list, max_length=50)
    languages: list[str] = Field(default_factory=list, max_length=30)
    manual_sections: list[Literal["experiences", "skills", "education", "languages"]] = Field(default_factory=list, max_length=4)
class InterviewAnswerRequest(BaseModel): question: str = Field(min_length=3, max_length=500); answer: str = Field(min_length=5, max_length=12000); context: str = Field(default="", max_length=4000)

@app.post("/api/interviews/evaluate")
async def evaluate_interview(req: InterviewAnswerRequest, user=Depends(authenticated_user), request: Request = None):
    if _document_export_metadata(user).get("plan") != "pro":
        raise HTTPException(
            402,
            detail={
                "code": "PRO_PLAN_REQUIRED",
                "message": "A avaliação de entrevista com IA está incluída no plano Pro.",
                "plans_url": "/#planos",
            },
        )
    if request is not None:
        _enforce_rate_limit(request, "ai-interview-evaluation", str(_owner_id(user) or ""))
    try:
        return await evaluate_interview_answer(req.question, req.answer, req.context)
    except AIProviderError as exc:
        logger.warning("Provedor de IA indisponivel na avaliacao de entrevista: %s", exc)
        raise HTTPException(503, "A analise nao esta disponivel agora. Tente novamente em instantes.") from exc


@app.get("/api/interviews/prep/{app_id}")
def interview_prep(app_id: int, user=Depends(authenticated_user)):
    """Monta um roteiro inicial de entrevista com base nos gaps da candidatura."""
    db = SessionLocal()
    try:
        application = _application_for_user(db, app_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        analysis: dict[str, Any] = {}
        if application.analysis_data:
            try:
                analysis = json.loads(application.analysis_data)
            except (TypeError, ValueError):
                analysis = {}
        if not isinstance(analysis, dict):
            analysis = {}

        def bounded_items(key: str) -> list[str]:
            values = analysis.get(key)
            if not isinstance(values, list):
                return []
            result: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                cleaned = value.strip()[:300]
                if cleaned:
                    result.append(cleaned)
                if len(result) >= 6:
                    break
            return result

        gaps = bounded_items("gaps")
        strengths = bounded_items("strengths")
        questions = [
            f"Conte uma situação em que você aplicou {gap} e qual foi o resultado."
            for gap in gaps
        ]
        if not questions:
            questions = [
                "Conte uma realização profissional relevante para esta vaga.",
                "Descreva uma situação difícil que você resolveu e o que aprendeu.",
                "Como você mede a qualidade do seu trabalho nesta área?",
            ]
        return {
            "application_id": application.id,
            "job_title": application.job.title,
            "company": application.job.company,
            "analysis_score": _score_percent(application.analysis_score),
            "gaps": gaps,
            "strengths": strengths,
            "questions": questions,
            "answer_framework": "Use contexto, ação e resultado; não invente experiências para preencher um gap.",
        }
    finally:
        db.close()

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
def _content_version(prefix: str, value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _add_event(db, app, status, note="", channel="", external_result=""):
    app.status = status
    event = ApplicationEvent(
        application_id=app.id,
        status=status,
        note=note or None,
        channel=channel or None,
        external_result=external_result or None,
        resume_version=app.resume_version,
        cover_letter_version=app.cover_letter_version,
    )
    db.add(event)
    return event
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


def _enforce_application_risk_gate(app, target_status: str):
    """Keep risky opportunities from being marked as submitted without review."""
    submission_statuses = {"CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO"}
    if target_status not in submission_statuses:
        return
    if app.fraud_suspected:
        raise HTTPException(
            409,
            "Esta oportunidade foi bloqueada por sinais de fraude e nao pode avancar.",
        )
    if (app.health_band or "").strip().upper() in {"DUVIDOSA", "SUSPEITA"} and not app.risk_reviewed_at:
        raise HTTPException(
            409,
            "Revise os sinais de risco antes de registrar o envio da candidatura.",
        )


def _serialize_app(a, include_document_paths: bool = True, include_cover_letter_text: bool = False):
    an = None
    if a.analysis_data:
        try: an = json.loads(a.analysis_data)
        except: pass
    raw_score = a.analysis_score
    if raw_score is None and isinstance(an, dict):
        raw_score = an.get("score")
    score = _score_percent(raw_score)
    if isinstance(an, dict) and an.get("score") is not None:
        an["score"] = score
    try: dr = json.loads(a.decision_reasons or "[]")
    except: dr = []
    try: fc = json.loads(a.field_confidence or "{}")
    except: fc = {}
    return {"id": a.id, "job_id": a.job_id, "candidate_id": a.candidate_id, "company": a.job.company, "job_title": a.job.title, "job_url": a.job.url, "status": a.status, "analysis_score": score, "personalization_score": a.personalization_score, "recommendation": a.recommendation, "queue_decision": a.queue_decision or "REVISAR", "decision_reasons": dr, "capture_confidence": a.capture_confidence, "field_confidence": fc, "analysis": an, "document_path": a.document_path if include_document_paths else None, "cover_letter_text": a.cover_letter_text if include_cover_letter_text else _cover_letter_preview(a.cover_letter_text), "cover_letter_path": a.cover_letter_path if include_document_paths else None, "resume_version": a.resume_version, "cover_letter_version": a.cover_letter_version, "health_score": a.health_score, "health_band": a.health_band, "health_signals": a.health_signals or [], "fraud_suspected": a.fraud_suspected, "risk_reviewed_at": a.risk_reviewed_at.isoformat() if a.risk_reviewed_at else None, "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(), "events": [{"id": e.id, "status": e.status, "note": e.note, "channel": e.channel, "external_result": e.external_result, "resume_version": e.resume_version, "cover_letter_version": e.cover_letter_version, "created_at": e.created_at.isoformat()} for e in a.events]}


def _score_percent(value):
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(score):
        return None
    return round(max(0.0, min(100.0, score)))
def _cand_prefs(cand):
    s = {}
    if cand and cand.preferences_data:
        try: s = json.loads(cand.preferences_data)
        except: pass
    preferences = normalize_preferences(s, target_roles=cand.target_roles if cand else "", location=cand.location if cand else "")
    expiry_preferences, _ = _parse_expiration_preferences(cand, utc_now())
    preferences["notify_expiring"] = expiry_preferences["notify_expiring"]
    preferences["notify_expiring_consent_at"] = expiry_preferences["notify_expiring_consent_at"]
    preferences["lifecycle_email_configured"] = select_email_transport(smtp_settings()) is not None
    return preferences
def _apply_decision(app, cand, analysis):
    r = decide_opportunity({"title": app.job.title, "company": app.job.company, "location": app.job.location, "modality": app.job.modality, "description": app.job.description, "salary": app.job.salary, "salary_min": app.job.salary_min, "salary_max": app.job.salary_max, "contract_type": app.job.contract_type}, analysis, _cand_prefs(cand), capture_confidence=app.capture_confidence)
    reasons = list(r["reasons"])
    health_band = (app.health_band or "").strip().upper()
    if app.fraud_suspected:
        r["decision"] = "DESCARTAR"
        reasons.extend(reason for reason in ("SAUDE_SUSPEITA", "FRAUDE_SUSPEITA") if reason not in reasons)
    elif health_band in {"DUVIDOSA", "SUSPEITA"}:
        r["decision"] = "REVISAR"
        health_reason = "SAUDE_SUSPEITA" if health_band == "SUSPEITA" else "SAUDE_DUVIDOSA"
        if health_reason not in reasons:
            reasons.append(health_reason)
    app.queue_decision = r["decision"]
    app.decision_reasons = json.dumps(reasons, ensure_ascii=False)


def _save_quality(app, q):
    previous_risk = (
        app.health_score,
        (app.health_band or "").strip().upper(),
        bool(app.fraud_suspected),
        json.dumps(app.health_signals or [], ensure_ascii=False, sort_keys=True),
    )
    app.capture_confidence = int(q["confidence"])
    app.field_confidence = json.dumps(q["field_confidence"], ensure_ascii=False)
    health = q.get("health")
    if isinstance(health, dict):
        app.health_score = health.get("score")
        app.health_band = health.get("band")
        app.health_signals = health.get("signals") or []
        app.fraud_suspected = bool(health.get("fraud_suspected", False))
        current_risk = (
            app.health_score,
            (app.health_band or "").strip().upper(),
            bool(app.fraud_suspected),
            json.dumps(app.health_signals or [], ensure_ascii=False, sort_keys=True),
        )
        if app.risk_reviewed_at and previous_risk != current_risk:
            app.risk_reviewed_at = None


def _refresh_application_risk(app):
    """Reassess stored job content before review or submission to cover legacy records."""
    job = app.job
    quality = assess_job_capture(_job_quality_payload(job))
    _save_quality(app, quality)
    _apply_decision(app, None, None)


def _job_quality_payload(job):
    return {
        "source": job.source or "",
        "title": job.title or "",
        "company": job.company or "",
        "location": job.location or "",
        "modality": job.modality or "",
        "contract_type": job.contract_type or "",
        "salary": job.salary or "",
        "url": job.url or "",
        "description": job.description or "",
    }


def _job_risk_content_signature(job):
    payload = _job_quality_payload(job)
    return tuple(str(payload.get(key) or "").strip() for key in (
        "source", "title", "company", "location", "modality",
        "contract_type", "salary", "url", "description",
    ))


def _save_analysis(app, analysis, cand):
    app.analysis_score = analysis["score"]
    app.recommendation = analysis["recommendation"]
    app.analysis_data = json.dumps(analysis, ensure_ascii=False)
    _apply_decision(app, cand, analysis)

@app.on_event("startup")
def startup():
    global _retention_task
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # PostgreSQL system-catalog reflection can exceed Supabase's statement
        # timeout as the schema grows. Its native idempotent DDL is cheaper and
        # avoids blocking a Render deployment on SQLAlchemy inspection.
        if engine.dialect.name == "postgresql":
            for table in ("generated_documents", "document_deliveries", "followup_email_outbox", "email_application_submissions", "copilot_preparations"):
                policy = f"{table}_owner"
                db.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                db.execute(text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_policies
                            WHERE schemaname = current_schema()
                              AND tablename = '{table}'
                              AND policyname = '{policy}'
                        ) THEN
                            CREATE POLICY {policy}
                                ON {table}
                                FOR ALL TO authenticated
                                USING (owner_id = auth.uid()::text)
                                WITH CHECK (owner_id = auth.uid()::text);
                        END IF;
                    END $$;
                """))
            # Dispatcher state stays server-only: RLS is enabled without an authenticated policy.
            db.execute(text("ALTER TABLE interview_email_outbox ENABLE ROW LEVEL SECURITY"))
            db.execute(text("ALTER TABLE expiring_job_email_outbox ENABLE ROW LEVEL SECURITY"))
            db.execute(text("ALTER TABLE job_ingestion_tasks ENABLE ROW LEVEL SECURITY"))
            db.execute(text("REVOKE ALL ON TABLE job_ingestion_tasks FROM anon, authenticated"))
            db.execute(text("ALTER TABLE job_ingestion_runs ENABLE ROW LEVEL SECURITY"))
            db.execute(text("REVOKE ALL ON TABLE job_ingestion_runs FROM anon, authenticated"))
            db.execute(text("ALTER TABLE billing_subscriptions ENABLE ROW LEVEL SECURITY"))
            db.execute(text("ALTER TABLE consultation_credits ENABLE ROW LEVEL SECURITY"))
            # Shared ingestion records are client-readable only while active;
            # writes stay on the server/service-role path and have no client policy.
            db.execute(text("ALTER TABLE job_listings ENABLE ROW LEVEL SECURITY"))
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = current_schema()
                          AND tablename = 'job_listings'
                          AND policyname = 'job_listings_active_read'
                    ) THEN
                        CREATE POLICY job_listings_active_read
                            ON job_listings
                            FOR SELECT TO anon, authenticated
                            USING (status = 'active');
                    END IF;
                END $$;
            """))
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = current_schema()
                          AND tablename = 'billing_subscriptions'
                          AND policyname = 'billing_subscriptions_owner'
                    ) THEN
                        CREATE POLICY billing_subscriptions_owner
                            ON billing_subscriptions
                            FOR ALL TO authenticated
                            USING (owner_id = auth.uid()::text)
                            WITH CHECK (owner_id = auth.uid()::text);
                    END IF;
                END $$;
            """))
            migrations = {
                "candidates": {
                    "owner_id": "VARCHAR(36)", "profile_data": "TEXT", "resume_filename": "TEXT", "preferences_data": "TEXT",
                },
                "jobs": {
                    "owner_id": "VARCHAR(36)", "contract_type": "VARCHAR(50) DEFAULT ''", "modality_confidence": "INTEGER", "salary_confidence": "INTEGER", "contract_confidence": "INTEGER", "salary_min": "INTEGER", "salary_max": "INTEGER", "valid_through": "TIMESTAMP WITH TIME ZONE",
                },
                "queue_items": {
                    "contract_type": "VARCHAR(50)", "salary": "VARCHAR(200)", "modality_confidence": "INTEGER", "salary_confidence": "INTEGER", "contract_confidence": "INTEGER", "salary_min": "INTEGER", "salary_max": "INTEGER",
                },
                "document_export_purchases": {
                    "application_id": "INTEGER", "payer_email": "VARCHAR(320)", "receipt_email_status": "VARCHAR(20) DEFAULT 'PENDING' NOT NULL", "receipt_email_started_at": "TIMESTAMP WITH TIME ZONE", "receipt_email_sent_at": "TIMESTAMP WITH TIME ZONE",
                    "document_generation_status": "VARCHAR(20) DEFAULT 'WAITING' NOT NULL", "document_generation_attempts": "INTEGER DEFAULT 0 NOT NULL", "document_generation_started_at": "TIMESTAMP WITH TIME ZONE", "document_generation_next_attempt_at": "TIMESTAMP WITH TIME ZONE", "document_generation_completed_at": "TIMESTAMP WITH TIME ZONE", "document_generation_error": "VARCHAR(240)", "payer_email_confirmed": "BOOLEAN DEFAULT FALSE NOT NULL",
                },
                "applications": {
                    "cover_letter_text": "TEXT", "cover_letter_path": "TEXT", "analysis_data": "TEXT", "decision_reasons": "TEXT", "field_confidence": "TEXT", "resume_version": "VARCHAR(32)", "cover_letter_version": "VARCHAR(32)", "health_score": "INTEGER", "health_band": "VARCHAR(20)", "health_signals": "JSON", "fraud_suspected": "BOOLEAN DEFAULT FALSE NOT NULL", "risk_reviewed_at": "TIMESTAMP WITH TIME ZONE", "queue_decision": "VARCHAR(20) DEFAULT 'REVISAR' NOT NULL", "capture_confidence": "INTEGER", "followup_notified_at": "TIMESTAMP WITH TIME ZONE", "followup_notification_outbox_id": "INTEGER",
                },
                "application_events": {
                    "channel": "VARCHAR(50)", "external_result": "VARCHAR(50)", "resume_version": "VARCHAR(32)", "cover_letter_version": "VARCHAR(32)",
                },
            }
            for table, columns in migrations.items():
                for column, ddl in columns.items():
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))
            for statement in (
                "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications (status)",
                "CREATE INDEX IF NOT EXISTS idx_applications_updated_at ON applications (updated_at)",
                "CREATE INDEX IF NOT EXISTS idx_applications_queue_decision ON applications (queue_decision)",
                "CREATE INDEX IF NOT EXISTS ix_applications_followup_notification_outbox_id ON applications (followup_notification_outbox_id)",
                "CREATE INDEX IF NOT EXISTS idx_candidates_owner_id ON candidates (owner_id)",
                "CREATE INDEX IF NOT EXISTS idx_jobs_owner_id ON jobs (owner_id)",
                "CREATE INDEX IF NOT EXISTS ix_jobs_valid_through ON jobs (valid_through)",
            ):
                db.execute(text(statement))
            db.commit()
            cleanup_expired_documents()
            _cleanup_generated_document_records()
            _backfill_legacy_generated_document_pairs()
            _cleanup_raw_intake_data()
            _cleanup_followup_email_outbox()
            _cleanup_interview_email_outbox()
            _cleanup_expiration_email_outbox()
            if _retention_task is None or _retention_task.done():
                _retention_task = asyncio.create_task(_document_retention_loop())
            _start_purchase_generation_worker()
            _start_lifecycle_email_worker()
            start_monitor()
            start_outlook_monitor()
            return
        for col in ["owner_id", "profile_data", "resume_filename", "preferences_data"]:
            if col not in {c["name"] for c in inspect(engine).get_columns("candidates")}:
                db.execute(text(f"ALTER TABLE candidates ADD COLUMN {col} {'VARCHAR(36)' if col == 'owner_id' else 'TEXT'}"))
        if "owner_id" not in {c["name"] for c in inspect(engine).get_columns("jobs")}:
            db.execute(text("ALTER TABLE jobs ADD COLUMN owner_id VARCHAR(36)"))
        job_columns = {c["name"] for c in inspect(engine).get_columns("jobs")}
        for col, ddl in {
            "contract_type": "VARCHAR(50) DEFAULT ''",
            "modality_confidence": "INTEGER",
            "salary_confidence": "INTEGER",
            "contract_confidence": "INTEGER",
            "salary_min": "INTEGER",
            "salary_max": "INTEGER",
            "valid_through": "TIMESTAMP WITH TIME ZONE",
        }.items():
            if col not in job_columns:
                db.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}"))
        queue_columns = {c["name"] for c in inspect(engine).get_columns("queue_items")}
        for col, ddl in {
            "contract_type": "VARCHAR(50)",
            "salary": "VARCHAR(200)",
            "modality_confidence": "INTEGER",
            "salary_confidence": "INTEGER",
            "contract_confidence": "INTEGER",
            "salary_min": "INTEGER",
            "salary_max": "INTEGER",
        }.items():
            if col not in queue_columns:
                db.execute(text(f"ALTER TABLE queue_items ADD COLUMN {col} {ddl}"))
        purchase_columns = {c["name"] for c in inspect(engine).get_columns("document_export_purchases")}
        for col, ddl in {
            "application_id": "INTEGER",
            "payer_email": "VARCHAR(320)",
            "receipt_email_status": "VARCHAR(20) DEFAULT 'PENDING' NOT NULL",
            "receipt_email_started_at": "TIMESTAMP WITH TIME ZONE",
            "receipt_email_sent_at": "TIMESTAMP WITH TIME ZONE",
            "document_generation_status": "VARCHAR(20) DEFAULT 'WAITING' NOT NULL",
            "document_generation_attempts": "INTEGER DEFAULT 0 NOT NULL",
            "document_generation_started_at": "TIMESTAMP WITH TIME ZONE",
            "document_generation_next_attempt_at": "TIMESTAMP WITH TIME ZONE",
            "document_generation_completed_at": "TIMESTAMP WITH TIME ZONE",
            "document_generation_error": "VARCHAR(240)",
            "payer_email_confirmed": "BOOLEAN DEFAULT FALSE NOT NULL",
        }.items():
            if col not in purchase_columns:
                db.execute(text(f"ALTER TABLE document_export_purchases ADD COLUMN {col} {ddl}"))
        application_columns = {c["name"] for c in inspect(engine).get_columns("applications")}
        for col in ["cover_letter_text", "cover_letter_path", "analysis_data", "decision_reasons", "field_confidence"]:
            if col not in application_columns:
                db.execute(text(f"ALTER TABLE applications ADD COLUMN {col} TEXT"))
        for col in ["resume_version", "cover_letter_version"]:
            if col not in application_columns:
                db.execute(text(f"ALTER TABLE applications ADD COLUMN {col} VARCHAR(32)"))
        for col, ddl in {
            "health_score": "INTEGER",
            "health_band": "VARCHAR(20)",
            "health_signals": "JSON",
            "fraud_suspected": "BOOLEAN DEFAULT FALSE NOT NULL",
            "risk_reviewed_at": "TIMESTAMP WITH TIME ZONE",
            "followup_notified_at": "TIMESTAMP WITH TIME ZONE",
            "followup_notification_outbox_id": "INTEGER",
        }.items():
            if col not in application_columns:
                db.execute(text(f"ALTER TABLE applications ADD COLUMN {col} {ddl}"))
        if "queue_decision" not in {c["name"] for c in inspect(engine).get_columns("applications")}:
            db.execute(text("ALTER TABLE applications ADD COLUMN queue_decision VARCHAR(20) DEFAULT 'REVISAR' NOT NULL"))
        if "capture_confidence" not in {c["name"] for c in inspect(engine).get_columns("applications")}:
            db.execute(text("ALTER TABLE applications ADD COLUMN capture_confidence INTEGER"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_applications_followup_notification_outbox_id ON applications (followup_notification_outbox_id)"))
        event_columns = {c["name"] for c in inspect(engine).get_columns("application_events")}
        for col in ["channel", "external_result"]:
            if col not in event_columns:
                db.execute(text(f"ALTER TABLE application_events ADD COLUMN {col} VARCHAR(50)"))
        for col in ["resume_version", "cover_letter_version"]:
            if col not in event_columns:
                db.execute(text(f"ALTER TABLE application_events ADD COLUMN {col} VARCHAR(32)"))
        for idx in ["idx_applications_status", "idx_applications_updated_at", "idx_applications_queue_decision", "idx_candidates_owner_id", "idx_jobs_owner_id"]:
            db.execute(text(f"CREATE INDEX IF NOT EXISTS {idx} ON {'applications' if 'applications' in idx else 'candidates' if 'candidates' in idx else 'jobs'} ({'status' if 'status' in idx else 'updated_at' if 'updated' in idx else 'queue_decision' if 'queue' in idx else 'owner_id'})"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_valid_through ON jobs (valid_through)"))
        for job in db.scalars(select(Job)).all():
            cand = db.scalar(select(Candidate).where(Candidate.owner_id == job.owner_id).order_by(Candidate.id))
            _ensure_app(db, job, cand)
        db.commit()
    finally:
        db.close()
    cleanup_expired_documents()
    _cleanup_generated_document_records()
    _backfill_legacy_generated_document_pairs()
    _cleanup_raw_intake_data()
    _cleanup_followup_email_outbox()
    _cleanup_interview_email_outbox()
    _cleanup_expiration_email_outbox()
    _cleanup_copilot_preparations()
    if _retention_task is None or _retention_task.done():
        _retention_task = asyncio.create_task(_document_retention_loop())
    _start_purchase_generation_worker()
    _start_lifecycle_email_worker()
    start_monitor()
    start_outlook_monitor()

@app.on_event("shutdown")
async def shutdown():
    global _retention_task, _purchase_generation_task, _purchase_generation_wakeup, _lifecycle_email_task
    if _retention_task is not None:
        _retention_task.cancel()
        try:
            await _retention_task
        except asyncio.CancelledError:
            pass
        _retention_task = None
    if _purchase_generation_task is not None:
        _purchase_generation_task.cancel()
        try:
            await _purchase_generation_task
        except asyncio.CancelledError:
            pass
        _purchase_generation_task = None
        _purchase_generation_wakeup = None
    if _lifecycle_email_task is not None:
        _lifecycle_email_task.cancel()
        try:
            await _lifecycle_email_task
        except asyncio.CancelledError:
            pass
        _lifecycle_email_task = None
    await stop_monitor()
    await stop_outlook_monitor()

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    if not LANDING_PATH.is_file():
        return {"agente": "Candidatura Certa", "status": "online", "version": "0.24.0", "dashboard": "/dashboard"}
    html = LANDING_PATH.read_text(encoding="utf-8")
    html = html.replace("<!-- CANDIDATURA_CERTA_DEMO_VIDEO -->", _landing_demo_video(), 1)
    html = _with_favicon(html)
    auth_script = (Path(__file__).parent / "static" / "landing-auth.js").read_text(encoding="utf-8")
    nonce = current_csp_nonce()
    html = _nonce_styles(html, nonce)
    rendered = html.replace(
        "</body>",
        _style_nonce_bootstrap(nonce)
        + f'<script src="/static/modal-a11y.js"></script><script src="/static/landing-enhance.js"></script><script nonce="{nonce}">' + auth_script + '</script><script src="/static/support-chat.js?v=6" defer></script></body>',
        1,
    )
    return HTMLResponse(rendered)

@app.head("/", include_in_schema=False)
def root_head():
    # Alguns monitores fazem HEAD na URL raiz; aproveite o ping para manter o banco ativo.
    health()
    return Response(status_code=200)

@app.get("/termos", response_class=HTMLResponse, include_in_schema=False)
def terms_page():
    nonce = current_csp_nonce()
    return HTMLResponse(_nonce_styles(_with_favicon(TERMS_PATH.read_text(encoding="utf-8")), nonce))

@app.get("/privacidade", response_class=HTMLResponse, include_in_schema=False)
def privacy_page():
    nonce = current_csp_nonce()
    return HTMLResponse(_nonce_styles(_with_favicon(PRIVACY_PATH.read_text(encoding="utf-8")), nonce))

@app.get("/auth/verification-required", response_class=HTMLResponse, include_in_schema=False)
def email_verification_page():
    if not EMAIL_VERIFICATION_PATH.is_file():
        raise HTTPException(500, "Pagina de confirmacao nao encontrada.")
    nonce = current_csp_nonce()
    return HTMLResponse(_nonce_styles(_with_favicon(EMAIL_VERIFICATION_PATH.read_text(encoding="utf-8")), nonce))

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

@app.get("/ajuda", response_class=HTMLResponse, include_in_schema=False)
def help_page():
    if not HELP_PAGE_PATH.is_file(): raise HTTPException(500, "Pagina de ajuda nao encontrada.")
    return _page(HELP_PAGE_PATH)

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
        education = data.get("education", [])
        languages = data.get("languages", [])
        manual_sections = data.get("_manual_sections", [])
        return {"configured": True, "name": c.name, "location": c.location, "email": c.email, "phone": c.phone, "linkedin": c.linkedin, "target_roles": _split_target_roles(c.target_roles), "summary": c.summary, "headline": data.get("headline", ""), "website": data.get("website", ""), "industry": data.get("industry", ""), "photo_data": data.get("photo_data", ""), "resume_filename": c.resume_filename, "experiences": len(c.experiences), "skills": len(c.skills), "experience_items": [{"role": e.role, "company": e.company, "start_date": e.start_date or "", "end_date": e.end_date or "", "period": " - ".join([v for v in (e.start_date, e.end_date) if v]), "description": e.description or ""} for e in c.experiences], "skill_items": [s.name for s in c.skills], "education_items": education if isinstance(education, list) else [], "language_items": languages if isinstance(languages, list) else [], "manual_sections": manual_sections if isinstance(manual_sections, list) else []}
    finally: db.close()


COPILOT_MONTHLY_LIMITS = {"essential": 30, "start": 150, "pro": 500, "consultoria": 500}
COPILOT_SUPPORTED_HOSTS = ("gupy.io", "vagas.com.br", "infojobs.com.br")


def _copilot_host_allowed(host: str) -> str | None:
    normalized = str(host or "").strip().lower().rstrip(".")
    if not normalized or "/" in normalized or ":" in normalized:
        return None
    return normalized if any(
        normalized == domain or normalized.endswith("." + domain)
        for domain in COPILOT_SUPPORTED_HOSTS
    ) else None


def _copilot_plan_usage(db, owner_id: str, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    period_start, period_end = month_window(current)
    subscription = db.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.owner_id == owner_id)
        .order_by(BillingSubscription.updated_at.desc())
        .limit(1)
    )
    plan = "essential"
    if subscription and _subscription_is_entitled(subscription):
        candidate_plan = str(subscription.plan_code or "").casefold()
        if candidate_plan in COPILOT_MONTHLY_LIMITS:
            plan = candidate_plan
    limit = COPILOT_MONTHLY_LIMITS[plan]
    used = int(db.scalar(
        select(func.count(CopilotPreparation.id)).where(
            CopilotPreparation.owner_id == owner_id,
            CopilotPreparation.created_at >= period_start,
            CopilotPreparation.created_at < period_end,
        )
    ) or 0)
    return {
        "plan_code": plan,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "period_start": period_start,
        "resets_at": period_end,
    }


def _copilot_profile_payload(db, user: dict) -> dict[str, Any]:
    candidate = _candidate_for_user(db, user)
    if candidate is None:
        raise HTTPException(409, "Complete e salve seu perfil antes de usar o copiloto.")
    try:
        raw = json.loads(candidate.profile_data or "{}")
        profile_data = raw if isinstance(raw, dict) else {}
    except (TypeError, ValueError):
        profile_data = {}

    def clean(value: Any, maximum: int) -> str:
        return sanitize_untrusted_text(str(value or ""), max_chars=maximum).strip()

    experiences = [{
        "role": clean(item.role, 200),
        "company": clean(item.company, 200),
        "period": clean(" - ".join(part for part in (item.start_date, item.end_date) if part), 100),
        "description": clean(item.description, 5000),
    } for item in candidate.experiences[:50]]
    raw_education = profile_data.get("education", [])
    education = []
    if isinstance(raw_education, list):
        for item in raw_education[:50]:
            if isinstance(item, str):
                education.append({"course": clean(item, 200), "institution": "", "period": ""})
            elif isinstance(item, dict):
                education.append({
                    "course": clean(item.get("course") or item.get("title"), 200),
                    "institution": clean(item.get("institution") or item.get("school"), 200),
                    "period": clean(item.get("period") or item.get("year"), 100),
                })
    raw_languages = profile_data.get("languages", [])
    languages = [clean(item, 100) for item in raw_languages[:30] if isinstance(item, str)] if isinstance(raw_languages, list) else []
    return {
        "name": clean(candidate.name, 180),
        "email": clean(user.get("email") or candidate.email, 240),
        "phone": clean(candidate.phone, 80),
        "linkedin": clean(candidate.linkedin, 500),
        "website": clean(profile_data.get("website"), 500),
        "location": clean(candidate.location, 180),
        "headline": clean(profile_data.get("headline"), 500),
        "summary": clean(candidate.summary, 5000),
        "experiences": experiences,
        "education": education,
        "skills": [clean(item.name, 200) for item in candidate.skills[:100]],
        "languages": languages,
    }


def _copilot_status_payload(db, owner_id: str) -> dict[str, Any]:
    usage = _copilot_plan_usage(db, owner_id)
    return {
        "plan_code": usage["plan_code"],
        "used": usage["used"],
        "limit": usage["limit"],
        "remaining": usage["remaining"],
        "resets_at": usage["resets_at"].isoformat(),
    }


def _copilot_json(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(payload, headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"})


@app.get("/api/copilot/status")
def copilot_status(request: Request, user=Depends(extension_authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    _enforce_rate_limit(request, "copilot-status", owner_id)
    db = SessionLocal()
    try:
        return _copilot_json(_copilot_status_payload(db, owner_id))
    finally:
        db.close()


@app.get("/api/copilot/profile")
def copilot_profile(request: Request, user=Depends(extension_authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    _enforce_rate_limit(request, "copilot-profile", owner_id)
    db = SessionLocal()
    try:
        return _copilot_json({"profile": _copilot_profile_payload(db, user), "usage": _copilot_status_payload(db, owner_id)})
    finally:
        db.close()


@app.get("/api/copilot/documents")
def copilot_documents(request: Request, user=Depends(extension_authenticated_user)):
    """List this user's unexpired generated-document pairs for optional attachment."""
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    _enforce_rate_limit(request, "copilot-documents", owner_id)
    result = list_generated_documents(user)
    items = [
        {
            "application_id": item["application_id"],
            "title": item["title"],
            "company": item["company"],
            "created_at": item["created_at"],
            "expires_at": item["expires_at"],
        }
        for item in result["items"]
        if item.get("application_id") is not None and item.get("resume") and item.get("cover_letter")
    ]
    return _copilot_json({"items": items})


@app.get("/api/copilot/documents/{application_id}/pdfs")
def copilot_application_pdfs(
    application_id: int,
    request: Request,
    user=Depends(extension_authenticated_user),
):
    """Return only current, owner-scoped PDFs for a chosen saved application."""
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    _enforce_rate_limit(request, "copilot-documents", owner_id)
    db = SessionLocal()
    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura não encontrada.")
        resume, letter = _current_application_documents(db, application, user)
        resume_pdf = docx_to_pdf(resume.content, title=resume.title or "Currículo")
        letter_pdf = docx_to_pdf(letter.content, title=letter.title or "Carta de apresentação")
        if len(resume_pdf) + len(letter_pdf) > 7 * 1024 * 1024:
            raise HTTPException(413, "Os PDFs excedem o limite combinado de 7 MB do complemento.")
        db.commit()
        return _copilot_json({
            "application_id": application.id,
            "title": application.job.title,
            "company": application.job.company,
            "resume": {
                "name": re.sub(r"[^A-Za-z0-9._-]", "-", Path(resume.filename).stem)[:115] + ".pdf",
                "base64": base64.b64encode(resume_pdf).decode("ascii"),
            },
            "letter": {
                "name": re.sub(r"[^A-Za-z0-9._-]", "-", Path(letter.filename).stem)[:115] + ".pdf",
                "base64": base64.b64encode(letter_pdf).decode("ascii"),
            },
        })
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Falha ao preparar PDFs do copiloto application_id=%s", application_id)
        if isinstance(exc, ValueError):
            raise HTTPException(409, "Não foi possível converter os documentos desta candidatura em PDF.") from exc
        raise
    finally:
        db.close()


@app.post("/api/copilot/prepare")
def copilot_prepare(
    payload: CopilotPrepareRequest,
    request: Request,
    user=Depends(extension_authenticated_user),
):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    if payload.analysis_only and not payload.consent_data_processing:
        raise HTTPException(403, "Autorize o envio do perfil e do texto da vaga para análise.")
    if not payload.analysis_only and not payload.portal_allowed:
        raise HTTPException(403, "Confirme que o portal permite preenchimento assistido.")
    portal_host = _copilot_host_allowed(payload.portal_host)
    if not portal_host:
        raise HTTPException(403, "O copiloto está habilitado somente para Gupy, Vagas.com e InfoJobs nesta versão.")
    try:
        request_id = str(uuid.UUID(payload.request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(422, "Identificador da preparação inválido.") from exc
    _enforce_rate_limit(request, "copilot-prepare", owner_id)
    db = SessionLocal()
    try:
        now = utc_now()
        period_start, _ = month_window(now)
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope), hashtext(:owner_period))"),
                {"scope": "copilot-monthly-limit", "owner_period": f"{owner_id}:{period_start.date().isoformat()}"},
            )
        if db.scalar(select(CopilotPreparation.id).where(
            CopilotPreparation.owner_id == owner_id,
            CopilotPreparation.request_id == request_id,
        )):
            raise HTTPException(409, "Esta preparação já foi iniciada. Atualize a página para começar outra.")
        usage = _copilot_plan_usage(db, owner_id, now)
        if usage["used"] >= usage["limit"]:
            raise HTTPException(
                403,
                f"Você atingiu o limite mensal de {usage['limit']} preparações assistidas do plano {usage['plan_code'].title()}. O limite será renovado em {usage['resets_at']:%d/%m/%Y}.",
                headers={"X-Copilot-Limit": "reached"},
            )
        profile = _copilot_profile_payload(db, user)
        if not any((profile["name"], profile["email"], profile["phone"])):
            raise HTTPException(409, "Complete e salve os dados básicos do seu perfil antes de continuar.")
        job_title = sanitize_untrusted_text(payload.job_title, max_chars=200).strip()
        job_company = sanitize_untrusted_text(payload.job_company, max_chars=200).strip()
        job_location = sanitize_untrusted_text(payload.job_location, max_chars=200).strip()
        job_description = sanitize_untrusted_text(payload.job_description, max_chars=12000).strip()
        vacancy_analysis = None
        ai_status = "not_requested"
        if job_description:
            analysis = analyze_job("\n".join((job_title, job_company, job_location, job_description)), profile)
            personalization = personalize_resume(job_title or "Oportunidade profissional", job_description, profile)
            vacancy_analysis = {
                "score": analysis["score"],
                "recommendation": analysis["recommendation"],
                "strengths": analysis["strengths"][:8],
                "gaps": analysis["gaps"][:8],
                "next_action": analysis["next_action"],
                "summary": sanitize_untrusted_text(personalization.get("tailored_summary", ""), max_chars=2000).strip(),
                "skills": [item["skill"] for item in personalization.get("prioritized_skills", [])[:8] if item.get("skill")],
                "experiences": [
                    {
                        "role": sanitize_untrusted_text(item.get("role", ""), max_chars=200).strip(),
                        "company": sanitize_untrusted_text(item.get("company", ""), max_chars=200).strip(),
                        "description": sanitize_untrusted_text(item.get("description", ""), max_chars=1200).strip(),
                    }
                    for item in personalization.get("prioritized_experiences", [])
                    if item.get("relevance_score", 0) > 0
                ][:3],
            }
            if payload.consent_gemini_processing:
                try:
                    suggestions = generate_copilot_suggestions(
                        {"title": job_title, "company": job_company, "location": job_location, "description": job_description},
                        profile,
                    )
                    vacancy_analysis["ai_suggestions"] = suggestions
                    if suggestions.get("tailored_summary"):
                        vacancy_analysis["summary"] = suggestions["tailored_summary"]
                    ai_status = "ready"
                except AIProviderError as exc:
                    logger.warning("Copiloto Gemini indisponível; mantendo análise determinística: %s", exc)
                    ai_status = "unavailable"
        db.add(CopilotPreparation(
            owner_id=owner_id,
            request_id=request_id,
            portal_host=portal_host,
            status="ANALYZED" if payload.analysis_only else "PREPARED",
            filled_count=0,
            consented_at=now,
            created_at=now,
        ))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Esta preparação já foi iniciada. Atualize a página para começar outra.") from exc
        usage["used"] += 1
        usage["remaining"] = max(0, usage["limit"] - usage["used"])
        return _copilot_json({
            "request_id": request_id,
            "profile": None if payload.analysis_only else profile,
            "vacancy_analysis": vacancy_analysis,
            "vacancy": {"title": job_title, "company": job_company, "location": job_location},
            "ai_status": ai_status,
            "usage": {
                "plan_code": usage["plan_code"],
                "used": usage["used"],
                "limit": usage["limit"],
                "remaining": usage["remaining"],
                "resets_at": usage["resets_at"].isoformat(),
            },
        })
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/api/copilot/complete")
def copilot_complete(
    payload: CopilotCompleteRequest,
    request: Request,
    user=Depends(extension_authenticated_user),
):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta da Candidatura Certa.")
    try:
        request_id = str(uuid.UUID(payload.request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(422, "Identificador da preparação inválido.") from exc
    _enforce_rate_limit(request, "copilot-complete", owner_id)
    db = SessionLocal()
    try:
        entry = db.scalar(select(CopilotPreparation).where(
            CopilotPreparation.owner_id == owner_id,
            CopilotPreparation.request_id == request_id,
        ))
        if entry is None:
            raise HTTPException(404, "A preparação não foi encontrada.")
        if entry.status == "PREPARED":
            entry.filled_count = payload.filled_count
            entry.status = "FILLED" if payload.filled_count else "NO_MATCH"
            entry.completed_at = utc_now()
            db.commit()
        return _copilot_json({"status": entry.status, "filled_count": entry.filled_count})
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()

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

@app.put("/profile/extracted")
def update_extracted_profile(req: ExtractedProfileUpdateRequest, user=Depends(authenticated_user)):
    """Replace the user's editable resume sections atomically and mark them as manual."""
    oid = str(_owner_id(user) or "").strip()
    if not oid:
        raise HTTPException(409, "Esta ação exige uma conta autenticada.")
    db = SessionLocal()
    try:
        c = db.scalar(select(Candidate).where(Candidate.owner_id == oid).order_by(Candidate.id))
        if c is None:
            raise HTTPException(409, "Salve as informações principais do perfil antes de editar os dados do currículo.")

        def clean(value: str, maximum: int) -> str:
            return sanitize_untrusted_text(value, max_chars=maximum).strip()

        experiences = []
        for item in req.experiences:
            role = clean(item.role, 200)
            if not role:
                raise HTTPException(422, "Cada experiência precisa informar o cargo.")
            experiences.append({
                "role": role,
                "company": clean(item.company, 200),
                "start_date": clean(item.start_date, 50),
                "end_date": clean(item.end_date, 50),
                "description": clean(item.description, 5000),
            })

        education = []
        for item in req.education:
            course = clean(item.course, 200)
            if not course:
                raise HTTPException(422, "Cada formação precisa informar o curso ou título.")
            education.append({
                "course": course,
                "institution": clean(item.institution, 200),
                "period": clean(item.period, 100),
            })

        skills = []
        seen_skills = set()
        for raw_skill in req.skills:
            name = clean(raw_skill, 200)
            if not name:
                continue
            key = name.casefold()
            if key not in seen_skills:
                seen_skills.add(key)
                skills.append(name)

        languages = []
        seen_languages = set()
        for raw_language in req.languages:
            language = clean(raw_language, 100)
            if not language:
                continue
            key = language.casefold()
            if key not in seen_languages:
                seen_languages.add(key)
                languages.append(language)

        profile_data = {}
        if c.profile_data:
            try:
                parsed_data = json.loads(c.profile_data)
                if isinstance(parsed_data, dict):
                    profile_data = parsed_data
            except (TypeError, ValueError):
                pass
        existing_manual = profile_data.get("_manual_sections", [])
        manual_sections = {
            section for section in existing_manual
            if isinstance(section, str) and section in PROFILE_EXTRACTED_SECTIONS
        } if isinstance(existing_manual, list) else set()
        requested_sections = set(req.manual_sections)
        manual_sections.update(requested_sections)

        if "experiences" in requested_sections:
            c.experiences.clear()
            for item in experiences:
                c.experiences.append(Experience(
                    company=item["company"], role=item["role"],
                    start_date=item["start_date"], end_date=item["end_date"],
                    description=item["description"],
                ))
        if "skills" in requested_sections:
            previous_skills = {skill.name.casefold(): skill for skill in c.skills if skill.name}
            c.skills.clear()
            for name in skills:
                previous = previous_skills.get(name.casefold())
                c.skills.append(Skill(
                    name=name,
                    category=previous.category if previous else "Manual",
                    proficiency=previous.proficiency if previous else "Não informada",
                ))
        if "education" in requested_sections:
            profile_data["education"] = education
        if "languages" in requested_sections:
            profile_data["languages"] = languages
        if manual_sections:
            profile_data["_manual_sections"] = sorted(manual_sections)
        c.profile_data = json.dumps(profile_data, ensure_ascii=False)
        if not requested_sections:
            return {"status": "SEM_ALTERACOES", "experiences": len(c.experiences), "skills": len(c.skills), "education": len(profile_data.get("education", [])), "languages": len(profile_data.get("languages", []))}
        db.commit()
        return {"status": "DADOS_DO_CURRICULO_ATUALIZADOS", "experiences": len(c.experiences), "skills": len(c.skills), "education": len(profile_data.get("education", [])), "languages": len(profile_data.get("languages", []))}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

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
        try:
            existing_preferences = json.loads(c.preferences_data or "{}")
        except (TypeError, ValueError):
            existing_preferences = {}
        previous_preferences = normalize_preferences(existing_preferences)
        prefs = normalize_preferences(req.model_dump())
        if req.notify_interviews and (req.notify_interviews_consent or previous_preferences["notify_interviews"]):
            prefs["notify_interviews"] = True
            prefs["notify_interviews_consent_at"] = (
                previous_preferences["notify_interviews_consent_at"] or utc_now().isoformat()
            )
        else:
            prefs["notify_interviews"] = False
            prefs["notify_interviews_consent_at"] = None
        previous_expiring, _ = _parse_expiration_preferences(c, utc_now())
        if req.notify_expiring and (req.notify_expiring_consent or previous_expiring["notify_expiring"]):
            prefs["notify_expiring"] = True
            prefs["notify_expiring_consent_at"] = (
                previous_expiring["notify_expiring_consent_at"] or utc_now().isoformat()
            )
        else:
            prefs["notify_expiring"] = False
            prefs["notify_expiring_consent_at"] = None
        if req.notify_followups:
            prefs["notify_followups"] = True
            prefs["notify_followups_consent_at"] = utc_now().isoformat()
        else:
            prefs["notify_followups"] = False
            prefs["notify_followups_consent_at"] = None
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
            # Incomplete parsers must not erase contact/profile values already
            # reviewed by the person. Non-empty resume values can still refresh
            # these fields; extracted sections have their own manual lock below.
            for field in ("name", "location", "email", "phone", "linkedin", "target_roles", "summary"):
                value = str(parsed.get(field) or "").strip()
                if value:
                    setattr(c, field, value)

        profile_data = {}
        if c.profile_data:
            try:
                existing_data = json.loads(c.profile_data)
                if isinstance(existing_data, dict):
                    profile_data = existing_data
            except (TypeError, ValueError):
                pass
        existing_manual_sections = profile_data.get("_manual_sections", [])
        manual_sections = {
            section for section in existing_manual_sections
            if isinstance(section, str) and section in PROFILE_EXTRACTED_SECTIONS
        } if isinstance(existing_manual_sections, list) else set()

        # Keep unrelated metadata and a previously saved headline. Only fill
        # missing extracted values; a reimport is not allowed to reset them.
        if not str(profile_data.get("headline") or "").strip() and str(parsed.get("headline") or "").strip():
            profile_data["headline"] = str(parsed["headline"]).strip()
        for section in ("education", "languages"):
            parsed_values = parsed.get(section)
            if section not in manual_sections and isinstance(parsed_values, list) and parsed_values:
                profile_data[section] = parsed_values
            elif section not in profile_data:
                profile_data[section] = parsed_values if isinstance(parsed_values, list) else []
        if manual_sections:
            profile_data["_manual_sections"] = sorted(manual_sections)
        c.profile_data = json.dumps(profile_data, ensure_ascii=False)
        c.resume_filename = parsed["source_filename"]
        if "experiences" not in manual_sections and parsed.get("experiences"):
            c.experiences.clear()
            for item in parsed["experiences"]:
                c.experiences.append(Experience(company=item.get("company", ""), role=item.get("role", ""), start_date=item.get("start_date", ""), end_date=item.get("end_date", ""), description=item.get("description", "")))
        if "skills" not in manual_sections and parsed.get("skills"):
            c.skills.clear()
            for skill in parsed["skills"]:
                c.skills.append(Skill(name=skill, category="Importada", proficiency="Nao informada"))
        db.commit()
        return {"status": "PERFIL_IMPORTADO", "name": c.name, "filename": c.resume_filename, "experiences": len(parsed.get("experiences") or []), "skills": len(parsed.get("skills") or []), "education": len(parsed.get("education") or []), "languages": len(parsed.get("languages") or [])}
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
        try:
            ensure_opportunity_capacity(db, oid)
        except PlanLimitReachedError as exc:
            raise HTTPException(429, str(exc)) from exc
        data = req.model_dump(); data["external_id"] = ext_id
        for field, limit in (("source", 50), ("company", 200), ("title", 200), ("location", 200), ("modality", 50), ("contract_type", 50), ("salary", 100), ("description", 80_000)):
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
        return {"status": "VAGA_CADASTRADA", "job": {"id": job.id, "source": job.source, "external_id": job.external_id, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "contract_type": job.contract_type, "modality_confidence": job.modality_confidence, "salary_confidence": job.salary_confidence, "contract_confidence": job.contract_confidence, "salary": job.salary, "salary_min": job.salary_min, "salary_max": job.salary_max, "valid_through": _job_deadline_iso(job.valid_through), "url": job.url}, "application": {"id": app.id, "status": app.status}}
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
            previous_job_signature = _job_risk_content_signature(existing)
            analysis = None
            if req.reprocess_existing:
                existing.source = parsed["source"]
                existing.company = parsed["company"]
                existing.title = parsed["title"]
                existing.description = parsed["description"]
                for f in ("location", "modality", "contract_type", "salary", "url"):
                    if parsed[f]:
                        setattr(existing, f, parsed[f])
                for f in ("modality_confidence", "salary_confidence", "contract_confidence", "salary_min", "salary_max"):
                    if parsed.get(f) is not None:
                        setattr(existing, f, parsed[f])
            if previous_job_signature != _job_risk_content_signature(existing):
                app.risk_reviewed_at = None
            _save_quality(app, assess_job_capture(_job_quality_payload(existing)))
            if req.reprocess_existing:
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
                "modality_confidence": parsed.get("modality_confidence", 0),
                "contract_type": parsed.get("contract_type", ""),
                "contract_confidence": parsed.get("contract_confidence", 0),
                "salary": existing.salary,
                "salary_confidence": parsed.get("salary_confidence", 0),
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
            "modality_confidence": parsed.get("modality_confidence", 0),
            "contract_type": parsed.get("contract_type", ""),
            "contract_confidence": parsed.get("contract_confidence", 0),
            "salary": parsed.get("salary", ""),
            "salary_confidence": parsed.get("salary_confidence", 0),
            "salary_min": parsed.get("salary_min"),
            "salary_max": parsed.get("salary_max"),
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
            "engine_version": f"0.24.0/{quality.get('heuristics_version', HEURISTICS_VERSION)}",
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
        "modality_confidence": parsed.get("modality_confidence", 0),
        "contract_type": parsed.get("contract_type", ""),
        "contract_confidence": parsed.get("contract_confidence", 0),
        "salary": parsed.get("salary", ""),
        "salary_confidence": parsed.get("salary_confidence", 0),
        "url": parsed.get("url"),
        }
    except PlanLimitReachedError as exc:
        db.rollback()
        raise HTTPException(429, str(exc)) from exc
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
            for f in ("title", "company", "description", "location", "modality", "salary", "url", "valid_through"):
                if structured.get(f): enriched[f] = structured[f]
            enriched["confidence"] = structured["confidence"]; enriched["method"] = structured["method"]
    selected = enriched or dict(parsed)
    confidence = int(selected.get("confidence", 55))
    method = selected.get("method", "local_ocr")
    if confidence >= 85:
        confirmed = await _run_document_work(
            confirm_job_intake,
            JobIntakeConfirmRequest(external_id=parsed["external_id"], source=parsed["source"], company=selected["company"], title=selected["title"], location=selected["location"], modality=selected["modality"], contract_type=selected.get("contract_type", parsed.get("contract_type", "")), modality_confidence=selected.get("modality_confidence", parsed.get("modality_confidence")), salary_confidence=selected.get("salary_confidence", parsed.get("salary_confidence")), contract_confidence=selected.get("contract_confidence", parsed.get("contract_confidence")), salary=selected["salary"], salary_min=selected.get("salary_min", parsed.get("salary_min")), salary_max=selected.get("salary_max", parsed.get("salary_max")), valid_through=selected.get("valid_through"), url=selected["url"], description=selected["description"], auto_analyze=True),
            user,
        )
        confirmed.update({
            "automatic": True,
            "confidence": confidence,
            "extraction_method": method,
            "modality_confidence": selected.get("modality_confidence", parsed.get("modality_confidence", 0)),
            "contract_type": selected.get("contract_type", parsed.get("contract_type", "")),
            "contract_confidence": selected.get("contract_confidence", parsed.get("contract_confidence", 0)),
            "salary_confidence": selected.get("salary_confidence", parsed.get("salary_confidence", 0)),
        })
        return confirmed
    return {"status": "REVISAO_NECESSARIA", "message": "Confianca abaixo do limite.", "external_id": parsed["external_id"], "source": parsed["source"], "company": selected["company"], "title": selected["title"], "location": selected["location"], "modality": selected["modality"], "modality_confidence": selected.get("modality_confidence", parsed.get("modality_confidence", 0)), "contract_type": selected.get("contract_type", parsed.get("contract_type", "")), "contract_confidence": selected.get("contract_confidence", parsed.get("contract_confidence", 0)), "salary": selected["salary"], "salary_confidence": selected.get("salary_confidence", parsed.get("salary_confidence", 0)), "valid_through": selected.get("valid_through"), "url": selected["url"], "description": selected["description"], "confidence": confidence, "extraction_method": method, "fetch_error": fetch_error, "extraction": {"method": ext["method"], "filename": ext["filename"], "characters": ext["characters"]}}

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
        if job is None:
            try:
                ensure_opportunity_capacity(db, oid)
            except PlanLimitReachedError as exc:
                raise HTTPException(429, str(exc)) from exc
        previous_job_signature = _job_risk_content_signature(job) if job is not None else None
        vals = {"source": sanitize_untrusted_text(req.source, max_chars=50).strip(), "company": sanitize_untrusted_text(req.company, max_chars=200).strip(), "title": sanitize_untrusted_text(req.title, max_chars=200).strip(), "location": sanitize_untrusted_text(req.location, max_chars=200).strip(), "modality": sanitize_untrusted_text(req.modality, max_chars=50).strip(), "contract_type": sanitize_untrusted_text(req.contract_type, max_chars=50).strip(), "modality_confidence": req.modality_confidence, "salary_confidence": req.salary_confidence, "contract_confidence": req.contract_confidence, "salary": sanitize_untrusted_text(req.salary, max_chars=100).strip(), "salary_min": req.salary_min, "salary_max": req.salary_max, "valid_through": req.valid_through, "url": req.url.strip()[:1000], "description": safe_description}
        if job is None:
            job = Job(owner_id=oid, external_id=ext_id, **vals); db.add(job); db.flush()
        else:
            for k, v in vals.items(): setattr(job, k, v)
        c = _candidate_for_user(db, user)
        app = _ensure_app(db, job, c)
        if previous_job_signature is not None and previous_job_signature != _job_risk_content_signature(job):
            app.risk_reviewed_at = None
        quality = assess_job_capture(_job_quality_payload(job))
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
        return {"status": "VAGA_ATUALIZADA" if updated else "VAGA_CAPTADA", "updated": updated, "job_id": job.id, "application_id": app.id, "application_status": app.status, "company": job.company, "job_title": job.title, "valid_through": _job_deadline_iso(job.valid_through), "analysis": analysis}
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
        return {"total": len(jobs), "jobs": [{"id": j.id, "source": j.source, "external_id": j.external_id, "company": j.company, "title": j.title, "location": j.location, "modality": j.modality, "contract_type": j.contract_type, "modality_confidence": j.modality_confidence, "salary_confidence": j.salary_confidence, "contract_confidence": j.contract_confidence, "salary": j.salary, "salary_min": j.salary_min, "salary_max": j.salary_max, "valid_through": _job_deadline_iso(j.valid_through), "url": j.url, "application_id": j.application.id if j.application else None, "application_status": j.application.status if j.application else None, "match_score": _score_percent(j.application.analysis_score) if j.application else None, "captured_at": j.application.created_at.isoformat() if j.application and j.application.created_at else None} for j in jobs]}
    finally: db.close()

@app.get("/jobs/{job_id}")
def get_job_endpoint(job_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        return {"id": job.id, "source": job.source, "external_id": job.external_id, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "contract_type": job.contract_type, "modality_confidence": job.modality_confidence, "salary_confidence": job.salary_confidence, "contract_confidence": job.contract_confidence, "salary": job.salary, "salary_min": job.salary_min, "salary_max": job.salary_max, "valid_through": _job_deadline_iso(job.valid_through), "url": job.url, "description": job.description, "application_id": job.application.id if job.application else None, "application_status": job.application.status if job.application else None}
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


@app.get("/applications/export.csv")
def export_applications_csv(status: str = None, decision: str = None, user=Depends(authenticated_user)):
    """Download an owner-scoped, privacy-conscious CSV of candidature tracking data."""
    if status and status not in APPLICATION_STATUSES:
        raise HTTPException(422, "Status invalido.")
    if decision and decision not in ("AUTOMATICA", "CAPTURAR", "REVISAR", "DESCARTAR"):
        raise HTTPException(422, "Decisao invalida.")
    db = SessionLocal()
    try:
        query = select(Application).join(Application.job).order_by(Application.updated_at.desc())
        oid = _owner_id(user)
        if oid:
            query = query.where(Job.owner_id == oid)
        if status:
            query = query.where(Application.status == status)
        if decision:
            query = query.where(Application.queue_decision == decision)
        applications = db.scalars(query).unique().all()

        def csv_cell(value: Any) -> str:
            text_value = "" if value is None else str(value)
            # Prevent spreadsheet applications from evaluating user-controlled
            # titles, companies or URLs as formulas when the CSV is opened.
            return "'" + text_value if text_value.startswith(("=", "+", "-", "@")) else text_value

        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow((
            "cargo", "empresa", "origem", "localidade", "modalidade",
            "tipo_contrato", "status", "decisao", "score_match",
            "data_captura", "data_atualizacao", "url_vaga",
        ))
        for application in applications:
            job = application.job
            writer.writerow((
                csv_cell(job.title),
                csv_cell(job.company),
                csv_cell(job.source),
                csv_cell(job.location),
                csv_cell(job.modality),
                csv_cell(job.contract_type),
                csv_cell(application.status),
                csv_cell(application.queue_decision or "REVISAR"),
                _score_percent(application.analysis_score),
                csv_cell(application.created_at.isoformat() if application.created_at else ""),
                csv_cell(application.updated_at.isoformat() if application.updated_at else ""),
                csv_cell(job.url),
            ))
        content = "\ufeff" + output.getvalue()
        response = Response(content=content, media_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = 'attachment; filename="candidaturas.csv"'
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        return response
    finally:
        db.close()

@app.get("/applications/metrics")
def application_metrics(user=Depends(authenticated_user)):
    """Return an owner-scoped funnel from captured jobs to qualified interviews."""
    db = SessionLocal()
    try:
        q = select(Application).join(Application.job).order_by(Application.created_at.asc())
        oid = _owner_id(user)
        if oid:
            q = q.where(Job.owner_id == oid)
        apps = db.scalars(q).all()

        submitted_statuses = {"CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"}
        submitted = 0
        interviews = 0
        by_source: dict[str, dict[str, int]] = {}
        by_channel: dict[str, dict[str, int]] = {}
        by_document_version: dict[tuple[str, str], dict[str, int]] = {}
        for item in apps:
            event_statuses = {event.status for event in item.events}
            sent_events = [event for event in item.events if event.status in submitted_statuses]
            submission_event = next((event for event in sent_events if event.status == "CANDIDATURA_ENVIADA"), sent_events[0] if sent_events else None)
            sent = submission_event is not None or item.status in submitted_statuses
            qualified = "ENTREVISTA" in event_statuses or any(event.external_result == "ENTREVISTA" for event in item.events) or item.status == "ENTREVISTA"
            if sent:
                submitted += 1
            if qualified:
                interviews += 1
            source = (item.job.source or "manual").strip().lower() or "manual"
            bucket = by_source.setdefault(source, {"captured": 0, "submitted": 0, "interviews": 0})
            bucket["captured"] += 1
            if sent:
                bucket["submitted"] += 1
            if qualified:
                bucket["interviews"] += 1
            if sent:
                channel = ((submission_event.channel if submission_event else None) or source).strip().lower() or "nao_informado"
                channel_bucket = by_channel.setdefault(channel, {"submitted": 0, "interviews": 0})
                channel_bucket["submitted"] += 1
                if qualified:
                    channel_bucket["interviews"] += 1
                resume_version = (submission_event.resume_version if submission_event else None) or item.resume_version or "sem-versao"
                cover_letter_version = (submission_event.cover_letter_version if submission_event else None) or item.cover_letter_version or "sem-versao"
                version_bucket = by_document_version.setdefault((resume_version, cover_letter_version), {"submitted": 0, "interviews": 0})
                version_bucket["submitted"] += 1
                if qualified:
                    version_bucket["interviews"] += 1

        def rate(value: int, base: int) -> float:
            return round((value / base) * 100, 1) if base else 0.0

        sources = []
        for source, values in sorted(by_source.items()):
            sources.append({
                "source": source,
                **values,
                "interview_rate_per_100": rate(values["interviews"], values["submitted"]),
            })
        channels = [{
            "channel": channel,
            **values,
            "interview_rate_per_100": rate(values["interviews"], values["submitted"]),
            "sample_sufficient": values["submitted"] >= 5,
        } for channel, values in sorted(by_channel.items())]
        versions = [{
            "resume_version": version[0],
            "cover_letter_version": version[1],
            **values,
            "interview_rate_per_100": rate(values["interviews"], values["submitted"]),
            "sample_sufficient": values["submitted"] >= 5,
        } for version, values in sorted(by_document_version.items())]
        return {
            "captured": len(apps),
            "submitted": submitted,
            "qualified_interviews": interviews,
            "interview_rate_per_100": rate(interviews, submitted),
            "by_source": sources,
            "by_channel": channels,
            "by_document_version": versions,
        }
    finally:
        db.close()


@app.get("/api/applications/followups")
def application_followups(user=Depends(authenticated_user)):
    """Lista candidaturas sem retorno que já merecem acompanhamento."""
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        query = select(Application).join(Application.job).order_by(Application.updated_at.asc())
        if oid:
            query = query.where(Job.owner_id == oid)
        applications = db.scalars(query).unique().all()
        now = utc_now()
        terminal = {"ENTREVISTA", "APROVADO", "RECUSADO", "ARQUIVADA"}
        items = []
        for application in applications:
            if application.status in terminal:
                continue
            sent_events = [event for event in application.events if event.status == "CANDIDATURA_ENVIADA"]
            sent_at = max((event.created_at for event in sent_events), default=None)
            if sent_at is None and application.status == "CANDIDATURA_ENVIADA":
                sent_at = application.updated_at or application.created_at
            if sent_at is None:
                continue
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=now.tzinfo)
            elapsed_days = max(0, (now - sent_at).days)
            if elapsed_days < 7:
                continue
            items.append({
                "application_id": application.id,
                "job_title": application.job.title,
                "company": application.job.company,
                "sent_at": sent_at.isoformat(),
                "days_waiting": elapsed_days,
                "message": "Olá, tudo bem? Gostaria de acompanhar o andamento da minha candidatura para esta oportunidade.",
            })
        return {"items": items, "followup_after_days": 7}
    finally:
        db.close()


@app.get("/api/privacy/export")
def privacy_export(user=Depends(authenticated_user)):
    """Exporta os dados pessoais do usuário sem tokens ou segredos de integração."""
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        candidate_query = select(Candidate)
        jobs_query = select(Job).order_by(Job.id.asc())
        purchases_query = select(DocumentExportPurchase).order_by(DocumentExportPurchase.created_at.asc())
        notification_query = select(FollowupEmailOutbox).order_by(FollowupEmailOutbox.created_at.asc())
        expiration_notification_query = select(ExpiringJobEmailOutbox).order_by(ExpiringJobEmailOutbox.created_at.asc())
        copilot_query = select(CopilotPreparation).order_by(CopilotPreparation.created_at.asc())
        if oid:
            candidate_query = candidate_query.where(Candidate.owner_id == oid)
            jobs_query = jobs_query.where(Job.owner_id == oid)
            purchases_query = purchases_query.where(DocumentExportPurchase.owner_id == oid)
            notification_query = notification_query.where(FollowupEmailOutbox.owner_id == oid)
            expiration_notification_query = expiration_notification_query.where(ExpiringJobEmailOutbox.owner_id == oid)
            copilot_query = copilot_query.where(CopilotPreparation.owner_id == oid)
        candidate = db.scalar(candidate_query)
        jobs = db.scalars(jobs_query).all()
        applications = [job.application for job in jobs if job.application is not None]
        purchases = db.scalars(purchases_query).all()
        notifications = db.scalars(notification_query).all()
        expiration_notifications = db.scalars(expiration_notification_query).all()
        copilot_preparations = db.scalars(copilot_query).all()

        def iso(value):
            return value.isoformat() if value else None

        profile = None
        if candidate:
            profile = {
                "name": candidate.name,
                "location": candidate.location,
                "email": candidate.email,
                "phone": candidate.phone,
                "linkedin": candidate.linkedin,
                "target_roles": candidate.target_roles,
                "summary": candidate.summary,
                "profile_data": candidate.profile_data,
                "resume_filename": candidate.resume_filename,
                "preferences_data": candidate.preferences_data,
                "experiences": [{"company": item.company, "role": item.role, "start_date": item.start_date, "end_date": item.end_date, "description": item.description} for item in candidate.experiences],
                "skills": [{"name": item.name, "category": item.category, "proficiency": item.proficiency} for item in candidate.skills],
            }
        return JSONResponse({
            "export_version": "1",
            "generated_at": iso(utc_now()),
            "profile": profile,
            "jobs": [{"id": job.id, "source": job.source, "company": job.company, "title": job.title, "location": job.location, "modality": job.modality, "contract_type": job.contract_type, "modality_confidence": job.modality_confidence, "salary_confidence": job.salary_confidence, "contract_confidence": job.contract_confidence, "salary": job.salary, "salary_min": job.salary_min, "salary_max": job.salary_max, "valid_through": iso(job.valid_through), "url": job.url, "description": job.description} for job in jobs],
            "applications": [{"id": item.id, "job_id": item.job_id, "status": item.status, "analysis_score": item.analysis_score, "personalization_score": item.personalization_score, "recommendation": item.recommendation, "queue_decision": item.queue_decision, "resume_version": item.resume_version, "cover_letter_version": item.cover_letter_version, "created_at": iso(item.created_at), "updated_at": iso(item.updated_at), "events": [{"status": event.status, "note": event.note, "channel": event.channel, "external_result": event.external_result, "resume_version": event.resume_version, "cover_letter_version": event.cover_letter_version, "created_at": iso(event.created_at)} for event in item.events]} for item in applications],
            "purchases": [{"order_nsu": item.order_nsu, "amount": item.amount, "paid_amount": item.paid_amount, "status": item.status, "created_at": iso(item.created_at), "paid_at": iso(item.paid_at)} for item in purchases],
            "followup_email_notifications": [{"frequency": item.frequency, "status": item.status, "application_count": len(item.application_ids or []), "scheduled_at": iso(item.scheduled_at), "sent_at": iso(item.sent_at)} for item in notifications],
            "expiring_job_email_notifications": [{"job_id": item.job_id, "deadline": item.deadline_key, "frequency": item.frequency, "status": item.status, "scheduled_at": iso(item.scheduled_at), "sent_at": iso(item.sent_at)} for item in expiration_notifications],
            "copilot_preparations": [{"portal_host": item.portal_host, "status": item.status, "filled_count": item.filled_count, "consented_at": iso(item.consented_at), "created_at": iso(item.created_at), "completed_at": iso(item.completed_at)} for item in copilot_preparations],
        }, headers={"Content-Disposition": 'attachment; filename="agente-candidaturas-dados.json"'})
    finally:
        db.close()


class AccountDeletionRequest(BaseModel):
    confirmation: str


ACCOUNT_DELETION_CONFIRMATION = "EXCLUIR MINHA CONTA"


def _delete_local_owner_data(db, owner_id: str) -> list[Path]:
    """Stage deletion of every local record owned by an account."""
    jobs = db.scalars(select(Job).where(Job.owner_id == owner_id)).unique().all()
    applications = [job.application for job in jobs if job.application is not None]
    paths: list[Path] = []
    for application in applications:
        for raw_path in (application.document_path, application.cover_letter_path):
            if not raw_path:
                continue
            try:
                paths.append(resolve_document_path(raw_path))
            except ValueError:
                logger.warning("Ignorando caminho de documento fora do armazenamento privado durante exclusao")

    for model, column in (
        (ExpiringJobEmailOutbox, ExpiringJobEmailOutbox.owner_id),
        (InterviewEmailOutbox, InterviewEmailOutbox.owner_id),
        (FollowupEmailOutbox, FollowupEmailOutbox.owner_id),
        (DocumentDelivery, DocumentDelivery.owner_id),
        (EmailApplicationSubmission, EmailApplicationSubmission.owner_id),
        (CopilotPreparation, CopilotPreparation.owner_id),
        (GeneratedDocument, GeneratedDocument.owner_id),
        (DocumentExportPurchase, DocumentExportPurchase.owner_id),
        (ConsultationCredit, ConsultationCredit.owner_id),
        (BillingSubscription, BillingSubscription.owner_id),
        (ProcessedEmailMessage, ProcessedEmailMessage.owner_id),
        (EmailIntegration, EmailIntegration.owner_id),
        (QueueItem, QueueItem.owner_id),
    ):
        for row in db.scalars(select(model).where(column == owner_id)).all():
            db.delete(row)
    for job in jobs:
        db.delete(job)
    for candidate in db.scalars(select(Candidate).where(Candidate.owner_id == owner_id)).all():
        db.delete(candidate)
    db.flush()
    return paths


def _require_owner_id(user: dict) -> str:
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta para acessar os documentos salvos.")
    return owner_id


def _document_expired(document: GeneratedDocument, now: datetime | None = None) -> bool:
    expires_at = document.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires_at <= current


def _serialize_generated_document(document: GeneratedDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "kind": document.kind,
        "version": document.version[:8],
        "filename": document.filename,
        "created_at": document.created_at.isoformat(),
        "expires_at": document.expires_at.isoformat(),
        "download_url": f"/api/documents/{document.id}/download",
        "download_pdf_url": f"/api/documents/{document.id}/download.pdf",
    }


@app.get("/api/documents")
def list_generated_documents(user=Depends(authenticated_user)):
    """List each generated CV/letter pair from the signed-in account only."""
    owner_id = _require_owner_id(user)
    db = SessionLocal()
    try:
        deliveries = db.scalars(
            select(DocumentDelivery)
            .where(DocumentDelivery.owner_id == owner_id)
            .order_by(DocumentDelivery.id.desc())
        ).all()
        items: list[dict[str, Any]] = []
        included_document_ids: set[int] = set()
        now = utc_now()
        for delivery in deliveries:
            resume = db.get(GeneratedDocument, delivery.resume_document_id)
            letter = db.get(GeneratedDocument, delivery.cover_letter_document_id)
            if (
                resume is None or letter is None
                or resume.owner_id != owner_id or letter.owner_id != owner_id
                or _document_expired(resume, now) or _document_expired(letter, now)
            ):
                continue
            included_document_ids.update((resume.id, letter.id))
            items.append({
                "delivery_id": delivery.id,
                "application_id": delivery.application_id,
                "title": resume.title or letter.title,
                "company": resume.company or letter.company,
                "created_at": max(resume.created_at, letter.created_at).isoformat(),
                "expires_at": min(resume.expires_at, letter.expires_at).isoformat(),
                "email_status": delivery.status,
                "email_attempts": delivery.attempt_count,
                "email_last_error": delivery.last_error,
                "email_sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
                "resume": _serialize_generated_document(resume),
                "cover_letter": _serialize_generated_document(letter),
            })
        standalone_documents = db.scalars(
            select(GeneratedDocument)
            .where(GeneratedDocument.owner_id == owner_id)
            .order_by(GeneratedDocument.created_at.desc())
        ).all()
        for document in standalone_documents:
            if document.id in included_document_ids or _document_expired(document, now):
                continue
            item = {
                "delivery_id": None,
                "application_id": document.application_id,
                "title": document.title,
                "company": document.company,
                "created_at": document.created_at.isoformat(),
                "expires_at": document.expires_at.isoformat(),
                "email_status": "NO_DELIVERY",
                "email_attempts": 0,
                "email_last_error": None,
                "email_sent_at": None,
                "resume": None,
                "cover_letter": None,
            }
            item["resume" if document.kind == "resume" else "cover_letter"] = _serialize_generated_document(document)
            items.append(item)
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return {"items": items, "retention_days": _generated_document_retention_days()}
    finally:
        db.close()


@app.get("/api/documents/{document_id}/download")
def download_generated_document(document_id: int, user=Depends(authenticated_user)):
    """Download one private generated file after checking ownership and expiry."""
    owner_id = _require_owner_id(user)
    db = SessionLocal()
    try:
        document = db.scalar(select(GeneratedDocument).where(
            GeneratedDocument.id == document_id,
            GeneratedDocument.owner_id == owner_id,
        ))
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        if _document_expired(document):
            raise HTTPException(410, "Este documento expirou. Gere novamente para renovar o acesso.")
        if not document.content.startswith(b"PK"):
            logger.error("DOCX inválido no armazenamento document_id=%s", document.id)
            raise HTTPException(404, "Documento não encontrado.")
        filename = re.sub(r"[^A-Za-z0-9._-]", "-", document.filename)[:180]
        return Response(
            content=document.content,
            media_type=DOCUMENT_MIME_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    finally:
        db.close()


@app.post("/api/documents/deliveries/{delivery_id}/retry")
def retry_document_delivery(
    delivery_id: int,
    user=Depends(authenticated_user),
    request: Request = None,
):
    """Retry sending the stored DOCX pair to the verified account address."""
    owner_id = _require_owner_id(user)
    if request is not None:
        _enforce_rate_limit(request, "document-email-retry", owner_id)
    db = SessionLocal()
    try:
        delivery = db.scalar(select(DocumentDelivery).where(
            DocumentDelivery.id == delivery_id,
            DocumentDelivery.owner_id == owner_id,
        ))
        if delivery is None:
            raise HTTPException(404, "Entrega de documentos não encontrada.")
        status = _send_document_delivery(db, delivery, user)
        db.refresh(delivery)
        return {
            "status": status,
            "email_status": delivery.status,
            "attempts": delivery.attempt_count,
            "message": delivery.last_error or (
                "Os dois documentos foram enviados ao e-mail confirmado da conta."
                if delivery.status == "SENT"
                else "Os arquivos continuam disponíveis na biblioteca."
            ),
        }
    finally:
        db.close()


def _supabase_auth_delete_config(user: dict) -> tuple[str, str, str]:
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    user_id = str(user.get("id") or "").strip()
    if not service_key or not supabase_url or not user_id:
        raise HTTPException(503, "A exclusao definitiva ainda nao esta configurada no servidor.")
    return supabase_url, service_key, user_id


async def _delete_supabase_auth_user(request: Request, user: dict) -> None:
    supabase_url, service_key, user_id = _supabase_auth_delete_config(user)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{supabase_url}/auth/v1/admin/users/{quote(user_id, safe='')}",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Nao foi possivel confirmar a exclusao no provedor de autenticacao.") from exc
    # A previous attempt may already have removed the identity while its
    # response was lost. Treating 404 as success makes the final step safely
    # retryable without touching any other account.
    if response.status_code not in {200, 204, 404}:
        logger.warning("Supabase recusou exclusao de conta status=%s", response.status_code)
        raise HTTPException(503, "Nao foi possivel confirmar a exclusao no provedor de autenticacao.")


@app.post("/api/privacy/delete-account")
async def delete_account(
    payload: AccountDeletionRequest,
    request: Request,
    user=Depends(authenticated_user),
):
    if payload.confirmation.strip().upper() != ACCOUNT_DELETION_CONFIRMATION:
        raise HTTPException(422, f"Digite exatamente: {ACCOUNT_DELETION_CONFIRMATION}.")
    owner_id = _owner_id(user)
    if not owner_id:
        raise HTTPException(401, "Login necessario.")
    # Catch missing server configuration before irreversibly purging local
    # records. Network/provider errors after commit remain explicitly retryable.
    _supabase_auth_delete_config(user)

    db = SessionLocal()
    paths: list[Path] = []
    try:
        paths = _delete_local_owner_data(db, owner_id)
        # Remove legacy filesystem copies while the Auth identity is intact.
        # A failure aborts the database transaction so the caller can retry
        # without losing access to the account.
        for path in set(paths):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Nao foi possivel remover documento privado durante exclusao: %s", path.name)
                raise HTTPException(
                    503,
                    "Nao foi possivel remover todos os arquivos privados da conta. Os dados e o acesso foram preservados; tente novamente.",
                ) from exc
        # Commit the local purge before deleting the identity-provider account.
        # If the database commit fails, Supabase Auth remains intact; deleting
        # Auth first could leave committed personal data with no account able
        # to access or request its removal.
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Falha na exclusao definitiva da conta")
        raise HTTPException(503, "Nao foi possivel excluir a conta agora. Tente novamente.") from exc
    finally:
        db.close()

    # The local personal data is already durably removed. Provider failures
    # are retryable and cannot roll back the database or strand local records
    # behind a deleted Auth identity.
    try:
        await _delete_supabase_auth_user(request, user)
    except HTTPException as exc:
        raise HTTPException(
            503,
            "Os dados locais foram excluidos, mas nao foi possivel confirmar a remocao da conta no provedor de autenticacao. Os dados locais nao serao restaurados; tente novamente para concluir.",
        ) from exc
    except Exception as exc:
        logger.exception("Falha ao encerrar identidade apos exclusao dos dados locais")
        raise HTTPException(
            503,
            "Os dados locais foram excluidos, mas nao foi possivel confirmar a remocao da conta no provedor de autenticacao. Os dados locais nao serao restaurados; tente novamente para concluir.",
        ) from exc

    response = JSONResponse({"deleted": True, "message": "Conta e dados excluidos."})
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")
    return response

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
def document_export_offer(application_id: int | None = None, user=Depends(authenticated_user)):
    offer = _document_export_metadata(user, application_id)
    return {
        "allowed": offer["allowed"],
        "price": offer["price"],
        "checkout_url": offer["checkout_url"],
        "checkout_ready": offer.get("checkout_ready", False),
        "message": "Download liberado." if offer["allowed"] else "A prévia é gratuita; o download completo está incluído no Start e no Pro, ou pode ser comprado à parte.",
    }


def _public_base_url() -> str:
    configured = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if configured.startswith("https://"):
        return configured
    return "https://candidaturacerta.com.br"


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
    if int(paid_amount) != int(purchase.amount):
        logger.warning(
            "Pagamento Mercado Pago com valor divergente order_nsu=%s esperado=%s recebido=%s",
            purchase.order_nsu,
            purchase.amount,
            paid_amount,
        )
        return "amount_mismatch"
    values: dict[str, Any] = {
        "status": "PAID",
        "transaction_nsu": transaction_nsu,
        "paid_amount": paid_amount,
        "paid_at": utc_now(),
        "document_generation_status": "WAITING",
        "document_generation_next_attempt_at": utc_now(),
        "document_generation_error": None,
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


@contextmanager
def _smtp_client(config: dict[str, object], *, timeout: float):
    """Open the configured relay using STARTTLS or implicit TLS on port 465."""
    host = str(config["host"])
    port = int(config["port"])
    if bool(config.get("use_ssl")):
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
            yield smtp
        return
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if bool(config["use_tls"]):
            smtp.starttls()
        yield smtp


def _brevo_api_key() -> str:
    """Return the optional Brevo HTTP API key without exposing its value."""
    return _shared_brevo_api_key()


def _email_transport_config() -> dict[str, object] | None:
    """Prefer Brevo HTTPS when configured; otherwise use the SMTP relay."""
    return select_email_transport(smtp_settings())


def _send_via_brevo_api(message: EmailMessage, *, timeout: float) -> None:
    """Compatibility wrapper around the shared Brevo API transport."""
    _shared_send_via_brevo_api(message, timeout=timeout, http_client_factory=httpx.Client)

def _set_email_transport_stage(exc: BaseException, stage: str) -> None:
    """Annotate a transport error without exposing credentials in its text."""
    try:
        setattr(exc, "smtp_stage", stage)
    except Exception:
        # Some third-party exception types can disallow custom attributes;
        # callers still retain their safe default stage in that case.
        return


def _send_email_message(message: EmailMessage, config: dict[str, object], *, timeout: float) -> str:
    """Send via Brevo HTTPS when configured, otherwise use the relay SMTP."""
    # Setting BREVO_API_KEY is the explicit opt-in for Brevo HTTPS delivery.
    if config.get("transport") == "brevo_api":
        try:
            _send_via_brevo_api(message, timeout=timeout)
        except Exception as exc:
            _set_email_transport_stage(exc, "api")
            raise
        return "api"
    try:
        # Connection and STARTTLS happen while entering this context manager.
        with _smtp_client(config, timeout=timeout) as smtp:
            try:
                smtp.login(str(config["username"]), str(config["password"]))
            except Exception as exc:
                _set_email_transport_stage(exc, "auth")
                raise
            try:
                smtp.send_message(message)
            except Exception as exc:
                _set_email_transport_stage(exc, "send")
                raise
    except Exception as exc:
        if not getattr(exc, "smtp_stage", None):
            _set_email_transport_stage(exc, "connect")
        raise
    return "smtp"


def _send_purchase_receipt(db, purchase: DocumentExportPurchase) -> str:
    """Send one plain-text receipt when SMTP is configured; retries stay idempotent."""
    locked = db.scalar(
        select(DocumentExportPurchase)
        .where(DocumentExportPurchase.id == purchase.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        return "missing"
    purchase = locked
    if purchase.receipt_email_status == "SENT":
        return "sent"
    if purchase.receipt_email_status == "SENDING" and purchase.receipt_email_started_at is not None:
        started = purchase.receipt_email_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if utc_now() - started < timedelta(minutes=15):
            return "sending"
    recipient = str(purchase.payer_email or "").strip()
    smtp_config = _email_transport_config()
    if not recipient or smtp_config is None:
        purchase.receipt_email_status = "SKIPPED"
        db.commit()
        return "skipped"
    sender = str(smtp_config["sender"])
    message = EmailMessage()
    message["Subject"] = "Comprovante da exportação — Candidatura Certa"
    message["From"] = sender
    message["To"] = recipient
    amount = f"R$ {int(purchase.paid_amount or purchase.amount) / 100:.2f}".replace(".", ",")
    message.set_content(
        "Pagamento confirmado na Candidatura Certa.\n\n"
        f"Pedido: {purchase.order_nsu}\nValor: {amount}\n"
        f"Transação: {purchase.transaction_nsu or 'confirmada'}\n\n"
        "O currículo e a carta ficarão disponíveis na biblioteca assim que a geração for concluída. "
        "Se o envio por e-mail estiver configurado, você também receberá os dois arquivos.\n\n"
        "Precisa de ajuda? contato@candidaturacerta.com.br | WhatsApp: (71) 99182-4951."
    )
    # Persist the attempt and release the row lock before network I/O. The
    # document worker can finish archiving while SMTP is slow or unavailable.
    purchase.receipt_email_status = "SENDING"
    purchase.receipt_email_started_at = utc_now()
    db.commit()
    smtp_stage = "api" if smtp_config.get("transport") == "brevo_api" else "connect"
    try:
        _send_email_message(message, smtp_config, timeout=10)
    except (OSError, smtplib.SMTPException, TimeoutError, httpx.HTTPError, ValueError, RuntimeError) as exc:
        smtp_stage = str(getattr(exc, "smtp_stage", smtp_stage))
        smtp_code = getattr(exc, "smtp_code", None)
        if not isinstance(smtp_code, int):
            smtp_code = None
        logger.warning(
            "Nao foi possivel enviar recibo order_nsu=%s smtp_stage=%s error_type=%s smtp_code=%s",
            purchase.order_nsu,
            smtp_stage,
            type(exc).__name__,
            smtp_code,
        )
        current = db.scalar(
            select(DocumentExportPurchase)
            .where(DocumentExportPurchase.id == purchase.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is not None and current.receipt_email_status != "SENT":
            current.receipt_email_status = "FAILED"
            current.receipt_email_started_at = None
            db.commit()
        return "failed"
    current = db.scalar(
        select(DocumentExportPurchase)
        .where(DocumentExportPurchase.id == purchase.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None:
        return "missing"
    if current.receipt_email_status != "SENT":
        current.receipt_email_status = "SENT"
        current.receipt_email_started_at = None
        current.receipt_email_sent_at = utc_now()
        db.commit()
    return "sent"


def _ensure_generated_document(
    db,
    *,
    owner_id: str,
    application: Application,
    kind: str,
    version: str,
    path: str | Path,
) -> GeneratedDocument:
    """Persist one validated DOCX version as a private PostgreSQL blob."""
    if kind not in {"resume", "cover_letter"}:
        raise ValueError("Tipo de documento inválido.")
    try:
        resolved = resolve_document_path(path)
    except ValueError as exc:
        raise HTTPException(500, "O documento não está no armazenamento privado.") from exc
    if not resolved.is_file():
        raise HTTPException(500, "O documento gerado não está disponível para arquivamento.")
    content = resolved.read_bytes()
    if not content.startswith(b"PK"):
        raise HTTPException(500, "O arquivo gerado não é um DOCX válido.")
    if len(content) > MAX_DOCUMENT_FILE_BYTES:
        raise HTTPException(413, "O documento excede o limite seguro de armazenamento.")

    existing = db.scalar(select(GeneratedDocument).where(
        GeneratedDocument.application_id == application.id,
        GeneratedDocument.owner_id == owner_id,
        GeneratedDocument.kind == kind,
        GeneratedDocument.version == version,
    ).with_for_update())
    now = utc_now()
    title = str(application.job.title or "Oportunidade")[:200]
    company = str(application.job.company or "Empresa não informada")[:200]
    filename = "curriculo.docx" if kind == "resume" else "carta.docx"
    expires_at = now + timedelta(days=_generated_document_retention_days())
    if existing is not None:
        # A previously expired version can be regenerated under the same content hash.
        existing.content = content
        existing.title = title
        existing.company = company
        existing.filename = filename
        existing.content_type = DOCUMENT_MIME_TYPE
        existing.created_at = now
        existing.expires_at = expires_at
        db.flush()
        return existing

    document = GeneratedDocument(
        owner_id=owner_id,
        application_id=application.id,
        kind=kind,
        version=version,
        title=title,
        company=company,
        filename=filename,
        content_type=DOCUMENT_MIME_TYPE,
        content=content,
        created_at=now,
        expires_at=expires_at,
    )
    try:
        # The application row is locked by the generation helper. The unique
        # constraint remains the final guard for old callers and multiple app
        # processes; use a savepoint so a losing concurrent insert can recover.
        with db.begin_nested():
            db.add(document)
            db.flush()
        return document
    except IntegrityError:
        existing = db.scalar(select(GeneratedDocument).where(
            GeneratedDocument.application_id == application.id,
            GeneratedDocument.owner_id == owner_id,
            GeneratedDocument.kind == kind,
            GeneratedDocument.version == version,
        ).with_for_update())
        if existing is None:
            raise
        existing.content = content
        existing.title = title
        existing.company = company
        existing.filename = filename
        existing.content_type = DOCUMENT_MIME_TYPE
        existing.created_at = now
        existing.expires_at = expires_at
        db.flush()
        return existing


def _ensure_document_delivery(
    db,
    *,
    owner_id: str,
    application_id: int,
    resume_document: GeneratedDocument,
    cover_letter_document: GeneratedDocument,
) -> DocumentDelivery:
    delivery = db.scalar(select(DocumentDelivery).where(
        DocumentDelivery.owner_id == owner_id,
        DocumentDelivery.resume_document_id == resume_document.id,
        DocumentDelivery.cover_letter_document_id == cover_letter_document.id,
    ))
    if delivery is None:
        delivery = DocumentDelivery(
            owner_id=owner_id,
            application_id=application_id,
            resume_document_id=resume_document.id,
            cover_letter_document_id=cover_letter_document.id,
            status="PENDING",
            attempt_count=0,
        )
        db.add(delivery)
        db.flush()
    return delivery


def _archive_application_documents(
    db,
    application: Application,
    user: dict,
) -> DocumentDelivery | None:
    """Archive every current file and create a delivery only when both exist."""
    owner_id = str(_owner_id(user) or application.job.owner_id or "").strip()
    if not owner_id:
        return None
    current: dict[str, GeneratedDocument] = {}
    for kind, raw_path, version in (
        ("resume", application.document_path, application.resume_version),
        ("cover_letter", application.cover_letter_path, application.cover_letter_version),
    ):
        if not raw_path:
            continue
        try:
            path = resolve_document_path(raw_path)
            if not path.is_file():
                continue
            content = path.read_bytes()
            if not content.startswith(b"PK") or len(content) > MAX_DOCUMENT_FILE_BYTES:
                logger.warning("Documento ignorado ao arquivar app_id=%s tipo=%s", application.id, kind)
                continue
            prefix = "cv" if kind == "resume" else "carta"
            document_version = version or f"{prefix}-{hashlib.sha256(content).hexdigest()[:12]}"
            current[kind] = _ensure_generated_document(
                db,
                owner_id=owner_id,
                application=application,
                kind=kind,
                version=document_version,
                path=path,
            )
        except (OSError, ValueError, HTTPException):
            # A stale legacy pointer must not break generating/downloading a new file.
            logger.warning("Documento legado indisponível ao arquivar app_id=%s tipo=%s", application.id, kind)
    resume = current.get("resume")
    letter = current.get("cover_letter")
    if resume is None or letter is None:
        return None
    return _ensure_document_delivery(
        db,
        owner_id=owner_id,
        application_id=application.id,
        resume_document=resume,
        cover_letter_document=letter,
    )


def _generate_and_archive_application_documents(
    db,
    *,
    application: Application,
    owner_id: str,
    user: dict,
) -> tuple[Application, DocumentDelivery]:
    """Generate and persist an owned resume/letter pair under an application lock."""
    locked_application = db.scalar(
        select(Application)
        .where(Application.id == application.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_application is None or str(locked_application.job.owner_id) != str(owner_id):
        raise HTTPException(404, "Candidatura nao encontrada.")
    application = locked_application
    job = application.job
    candidate = _candidate_for_user(db, user)
    if candidate is None:
        raise HTTPException(404, "Perfil profissional nao encontrado.")
    arts = _build_application(job, candidate)

    resume_path: Path | None = None
    letter_path: Path | None = None
    if application.document_path:
        try:
            candidate_path = resolve_document_path(application.document_path)
            if candidate_path.is_file():
                resume_path = candidate_path
        except ValueError:
            resume_path = None
    if application.cover_letter_path:
        try:
            candidate_path = resolve_document_path(application.cover_letter_path)
            if candidate_path.is_file():
                letter_path = candidate_path
        except ValueError:
            letter_path = None

    letter = application.cover_letter_text or generate_cover_letter(
        job_title=job.title,
        company=job.company,
        profile=arts["profile"],
        analysis=arts["analysis"],
        personalization=arts["personalization"],
    )
    if resume_path is None:
        resume_path = Path(generate_docx(arts["resume"])).resolve()
    if letter_path is None:
        letter_path = Path(
            generate_cover_letter_docx(letter=letter, company=job.company, job_title=job.title)
        ).resolve()
    if not resume_path.is_file():
        raise HTTPException(500, "Curriculo nao foi criado.")
    if not letter_path.is_file():
        raise HTTPException(500, "Carta nao foi criada.")

    _save_analysis(application, arts["analysis"], candidate)
    application.personalization_score = arts["personalization"].get("personalization_score", 0)
    application.document_path = str(resume_path)
    application.cover_letter_text = letter
    application.cover_letter_path = str(letter_path)
    application.resume_version = _content_version("cv", arts["resume"])
    application.cover_letter_version = _content_version("carta", letter)
    _advance_app(db, application, "CURRICULO_GERADO", "Curriculo e carta personalizados liberados apos pagamento.")

    resume_document = _ensure_generated_document(
        db,
        owner_id=owner_id,
        application=application,
        kind="resume",
        version=application.resume_version,
        path=resume_path,
    )
    letter_document = _ensure_generated_document(
        db,
        owner_id=owner_id,
        application=application,
        kind="cover_letter",
        version=application.cover_letter_version,
        path=letter_path,
    )
    delivery = _ensure_document_delivery(
        db,
        owner_id=owner_id,
        application_id=application.id,
        resume_document=resume_document,
        cover_letter_document=letter_document,
    )
    return application, delivery


def _purchase_generation_payload(purchase: DocumentExportPurchase) -> dict[str, Any]:
    status = str(purchase.document_generation_status or "WAITING").upper()
    messages = {
        "WAITING": "Pagamento confirmado. Estamos preparando seu currículo e sua carta.",
        "PROCESSING": "Pagamento confirmado. Estamos preparando seu currículo e sua carta.",
        "RETRY": "A geração está sendo repetida automaticamente. Seus documentos ficarão disponíveis em breve.",
        "READY": "Currículo e carta prontos para baixar.",
        "FAILED": "Não foi possível concluir a geração automaticamente. Tente gerar novamente; seu pagamento está preservado.",
    }
    return {
        "purchase_status": str(purchase.status or "PENDING").upper(),
        "generation_status": status,
        "attempts": int(purchase.document_generation_attempts or 0),
        "message": messages.get(status, "Aguardando a confirmação do pagamento."),
        "application_id": purchase.application_id,
    }


def _claim_paid_document_purchase(
    *,
    purchase_id: int | None = None,
    owner_id: str | None = None,
    application_id: int | None = None,
    allow_failed: bool = False,
) -> tuple[str, int | None]:
    """Atomically claim one persisted paid export; PostgreSQL skips other workers."""
    db = SessionLocal()
    try:
        if not inspect(db.get_bind()).has_table(DocumentExportPurchase.__tablename__):
            return "none", None
        now = utc_now()
        stale_before = now - DOCUMENT_GENERATION_STALE_AFTER
        eligible = ["WAITING", "RETRY"]
        if allow_failed:
            eligible.append("FAILED")
        claimable = (
            DocumentExportPurchase.document_generation_status.in_(eligible)
            & (
                DocumentExportPurchase.document_generation_next_attempt_at.is_(None)
                | (DocumentExportPurchase.document_generation_next_attempt_at <= now)
            )
        )
        if purchase_id is not None and allow_failed:
            # An owner-triggered retry may bypass the exhausted-backoff state.
            claimable = claimable | (DocumentExportPurchase.document_generation_status == "FAILED")
        query = select(DocumentExportPurchase).where(
            DocumentExportPurchase.status == "PAID",
            (
                claimable
                | (
                    (DocumentExportPurchase.document_generation_status == "PROCESSING")
                    & DocumentExportPurchase.document_generation_started_at.is_not(None)
                    & (DocumentExportPurchase.document_generation_started_at <= stale_before)
                )
            ),
        )
        if purchase_id is not None:
            query = query.where(DocumentExportPurchase.id == purchase_id)
        if owner_id is not None:
            query = query.where(DocumentExportPurchase.owner_id == str(owner_id))
        if application_id is not None:
            query = query.where(DocumentExportPurchase.application_id == application_id)
        query = query.order_by(DocumentExportPurchase.id).limit(1).with_for_update(skip_locked=True)
        purchase = db.scalar(query)

        if purchase is None and purchase_id is not None:
            # Surface READY and actively-processing states to an owner retry call.
            existing_query = select(DocumentExportPurchase).where(
                DocumentExportPurchase.id == purchase_id,
                DocumentExportPurchase.status == "PAID",
            )
            if owner_id is not None:
                existing_query = existing_query.where(DocumentExportPurchase.owner_id == str(owner_id))
            if application_id is not None:
                existing_query = existing_query.where(DocumentExportPurchase.application_id == application_id)
            current = db.scalar(existing_query)
            if current is None:
                return "missing", None
            current_status = str(current.document_generation_status or "WAITING").upper()
            if current_status == "READY":
                return "ready", current.id
            started = current.document_generation_started_at
            if current_status == "PROCESSING" and started is not None:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                if now - started < DOCUMENT_GENERATION_STALE_AFTER:
                    return "processing", current.id
            return "not_claimed", current.id

        if purchase is None:
            return "none", None

        attempts = int(purchase.document_generation_attempts or 0)
        if attempts >= DOCUMENT_GENERATION_MAX_ATTEMPTS and not allow_failed:
            purchase.document_generation_status = "FAILED"
            purchase.document_generation_error = "Geração não concluída após as tentativas automáticas."
            purchase.document_generation_next_attempt_at = None
            db.commit()
            return "failed", purchase.id
        if str(purchase.document_generation_status or "").upper() == "FAILED" and allow_failed:
            attempts = 0
        purchase.document_generation_status = "PROCESSING"
        purchase.document_generation_attempts = attempts + 1
        purchase.document_generation_started_at = now
        purchase.document_generation_next_attempt_at = None
        purchase.document_generation_error = None
        claimed_id = purchase.id
        db.commit()
        return "claimed", claimed_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _finish_paid_document_purchase(purchase_id: int) -> dict[str, Any]:
    """Generate/archive a claimed purchase; SMTP is isolated after READY commits."""
    db = SessionLocal()
    try:
        purchase = db.scalar(
            select(DocumentExportPurchase)
            .where(DocumentExportPurchase.id == purchase_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if purchase is None or purchase.status != "PAID":
            db.rollback()
            return {"generation_status": "MISSING"}
        if purchase.document_generation_status == "READY":
            return _purchase_generation_payload(purchase)
        if purchase.application_id is None:
            raise HTTPException(409, "Compra sem candidatura vinculada.")
        owner_id = str(purchase.owner_id)
        application = db.scalar(
            select(Application)
            .join(Application.job)
            .where(Application.id == purchase.application_id, Job.owner_id == owner_id)
        )
        if application is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        user = {
            "id": owner_id,
            "email": str(purchase.payer_email or "").strip(),
            "email_confirmed_at": bool(purchase.payer_email_confirmed),
        }
        application, delivery = _generate_and_archive_application_documents(
            db,
            application=application,
            owner_id=owner_id,
            user=user,
        )
        purchase.document_generation_status = "READY"
        purchase.document_generation_completed_at = utc_now()
        purchase.document_generation_started_at = None
        purchase.document_generation_next_attempt_at = None
        purchase.document_generation_error = None
        db.commit()
        generation_result = {
            "generation_status": "READY",
            "application_id": application.id,
            "job_id": application.job_id,
            "resume_url": f"/applications/{application.id}/document",
            "letter_url": f"/applications/{application.id}/cover-letter/document",
            "delivery_id": delivery.id,
            "message": "Currículo e carta prontos para baixar.",
        }
        try:
            email_status = _send_document_delivery(db, delivery, user)
            db.refresh(delivery)
            generation_result["email_status"] = email_status
            generation_result["email_message"] = delivery.last_error or (
                "Currículo e carta enviados para o e-mail confirmado da conta."
                if email_status == "sent"
                else "Currículo e carta estão disponíveis na biblioteca de documentos."
            )
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Falha não bloqueante ao enviar documentos da compra id=%s tipo=%s",
                purchase_id,
                type(exc).__name__,
            )
            generation_result["email_status"] = "FAILED"
            generation_result["email_message"] = "Currículo e carta estão prontos na biblioteca; o envio por e-mail pode ser tentado novamente."
        return generation_result
    except Exception as exc:
        db.rollback()
        purchase = db.get(DocumentExportPurchase, purchase_id)
        if purchase is not None and purchase.status == "PAID" and purchase.document_generation_status != "READY":
            attempts = int(purchase.document_generation_attempts or 1)
            if attempts < DOCUMENT_GENERATION_MAX_ATTEMPTS:
                purchase.document_generation_status = "RETRY"
                delay_index = min(max(attempts - 1, 0), len(DOCUMENT_GENERATION_BACKOFF_SECONDS) - 1)
                purchase.document_generation_next_attempt_at = utc_now() + timedelta(
                    seconds=DOCUMENT_GENERATION_BACKOFF_SECONDS[delay_index]
                )
                purchase.document_generation_error = "Não foi possível gerar os documentos agora; haverá nova tentativa automática."
            else:
                purchase.document_generation_status = "FAILED"
                purchase.document_generation_next_attempt_at = None
                purchase.document_generation_error = "Geração não concluída após as tentativas automáticas."
            purchase.document_generation_started_at = None
            db.commit()
            logger.warning(
                "Falha ao gerar documentos pagos purchase_id=%s attempt=%s type=%s",
                purchase_id,
                attempts,
                type(exc).__name__,
            )
            return _purchase_generation_payload(purchase)
        logger.warning("Falha ao reconciliar compra paga purchase_id=%s type=%s", purchase_id, type(exc).__name__)
        return {"generation_status": "FAILED", "message": "Não foi possível consultar esta geração."}
    finally:
        db.close()


def _process_pending_document_export_purchases(limit: int = 5) -> int:
    processed = 0
    for _ in range(max(1, min(int(limit), 20))):
        claim_status, purchase_id = _claim_paid_document_purchase()
        if claim_status == "none" or purchase_id is None:
            break
        if claim_status == "claimed":
            _finish_paid_document_purchase(purchase_id)
            processed += 1
    return processed


def _backfill_legacy_generated_document_pairs() -> int:
    """Import existing saved DOCX files without re-sending e-mail."""
    db = SessionLocal()
    imported = 0
    try:
        applications = db.scalars(select(Application).where(
            (Application.document_path.is_not(None))
            | (Application.cover_letter_path.is_not(None))
        )).all()
        for application in applications:
            owner_id = str(application.job.owner_id or "").strip()
            if not owner_id:
                continue
            document_specs = (
                ("resume", application.document_path, application.resume_version),
                ("cover_letter", application.cover_letter_path, application.cover_letter_version),
            )
            imported_documents: dict[str, GeneratedDocument] = {}
            for kind, raw_path, stored_version in document_specs:
                if not raw_path:
                    continue
                try:
                    path = resolve_document_path(raw_path)
                    if not path.is_file():
                        continue
                    content = path.read_bytes()
                    if not content.startswith(b"PK") or len(content) > MAX_DOCUMENT_FILE_BYTES:
                        continue
                    prefix = "cv" if kind == "resume" else "carta"
                    version = stored_version or f"{prefix}-{hashlib.sha256(content).hexdigest()[:12]}"
                    imported_documents[kind] = _ensure_generated_document(
                        db,
                        owner_id=owner_id,
                        application=application,
                        kind=kind,
                        version=version,
                        path=path,
                    )
                except (OSError, ValueError, HTTPException):
                    continue
            imported += len(imported_documents)
            resume = imported_documents.get("resume")
            letter = imported_documents.get("cover_letter")
            if resume is None or letter is None:
                continue
            delivery = db.scalar(select(DocumentDelivery).where(
                DocumentDelivery.owner_id == owner_id,
                DocumentDelivery.resume_document_id == resume.id,
                DocumentDelivery.cover_letter_document_id == letter.id,
            ))
            if delivery is None:
                delivery = _ensure_document_delivery(
                    db,
                    owner_id=owner_id,
                    application_id=application.id,
                    resume_document=resume,
                    cover_letter_document=letter,
                )
                delivery.status = "SKIPPED"
                delivery.last_error = "Versão anterior à biblioteca; o envio por e-mail não foi repetido automaticamente."
        db.commit()
        return imported
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _send_document_delivery(db, delivery: DocumentDelivery, user: dict) -> str:
    """Send both DOCX files to the verified account e-mail with retry state."""
    if delivery.status == "SENT":
        return "sent"
    if not _owner_id(user) or str(_owner_id(user)) != str(delivery.owner_id):
        raise HTTPException(404, "Entrega de documentos não encontrada.")

    resume = db.get(GeneratedDocument, delivery.resume_document_id)
    letter = db.get(GeneratedDocument, delivery.cover_letter_document_id)
    now = utc_now()
    if (
        resume is None
        or letter is None
        or resume.owner_id != delivery.owner_id
        or letter.owner_id != delivery.owner_id
        or _document_expired(resume, now)
        or _document_expired(letter, now)
    ):
        delivery.status = "SKIPPED"
        delivery.last_error = "Os documentos expiraram; gere novamente para renovar o acesso."
        db.commit()
        return "expired"

    recipient = str(user.get("email") or "").strip()
    if not recipient or not (user.get("email_confirmed_at") or user.get("confirmed_at")):
        delivery.status = "SKIPPED"
        delivery.last_error = "Confirme o e-mail da sua conta para receber os documentos."
        delivery.last_attempt_at = now
        db.commit()
        return "skipped"

    smtp_config = _email_transport_config()
    if smtp_config is None:
        delivery.status = "SKIPPED"
        delivery.last_error = "Envio por e-mail indisponível; os arquivos estão na biblioteca."
        delivery.last_attempt_at = now
        db.commit()
        return "skipped"
    sender = str(smtp_config["sender"])

    if len(resume.content) + len(letter.content) > MAX_DOCUMENT_EMAIL_BYTES:
        delivery.status = "SKIPPED"
        delivery.last_error = "Os arquivos excedem o limite de anexos; baixe-os pela biblioteca."
        delivery.last_attempt_at = now
        db.commit()
        return "skipped"

    # Row locking prevents concurrent browser retries from sending the same pair twice.
    locked = db.scalar(
        select(DocumentDelivery)
        .where(DocumentDelivery.id == delivery.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise HTTPException(404, "Entrega de documentos não encontrada.")
    if locked.status == "SENT":
        return "sent"
    if locked.status == "SENDING" and locked.last_attempt_at is not None:
        last_attempt = locked.last_attempt_at
        if last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=timezone.utc)
        if now - last_attempt < timedelta(minutes=15):
            return "sending"

    locked.status = "SENDING"
    locked.attempt_count += 1
    locked.last_attempt_at = now
    locked.last_error = None
    db.commit()

    message = EmailMessage()
    message["Subject"] = "Seu currículo e sua carta estão prontos"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "Olá! Seu currículo personalizado e sua carta de apresentação foram gerados. "
        "Os dois arquivos DOCX seguem anexos. Você também pode baixá-los na aba "
        "na biblioteca de documentos da Candidatura Certa enquanto estiverem dentro do prazo de retenção."
    )
    message.add_attachment(
        resume.content,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=resume.filename,
    )
    message.add_attachment(
        letter.content,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=letter.filename,
    )
    smtp_stage = "api" if smtp_config.get("transport") == "brevo_api" else "connect"
    try:
        _send_email_message(message, smtp_config, timeout=15)
    except (OSError, smtplib.SMTPException, TimeoutError, httpx.HTTPError, ValueError, RuntimeError) as exc:
        smtp_stage = str(getattr(exc, "smtp_stage", smtp_stage))
        smtp_code = getattr(exc, "smtp_code", None)
        if not isinstance(smtp_code, int):
            smtp_code = None
        logger.warning(
            "Falha no envio de documentos delivery_id=%s smtp_stage=%s error_type=%s smtp_code=%s",
            delivery.id,
            smtp_stage,
            type(exc).__name__,
            smtp_code,
        )
        locked.status = "FAILED"
        locked.last_error = "Falha de transporte SMTP; tente novamente."
        db.commit()
        return "failed"

    locked.status = "SENT"
    locked.sent_at = utc_now()
    locked.last_error = None
    db.commit()
    return "sent"


@app.post("/billing/subscriptions/checkout")
async def create_subscription_checkout(req: SubscriptionCheckoutRequest, request: Request, user=Depends(authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    email = str(user.get("email") or "").strip()
    plan = SUBSCRIPTION_PLANS.get(req.plan_code)
    if not owner_id or not email:
        raise HTTPException(409, "Entre na sua conta para iniciar uma assinatura.")
    _enforce_rate_limit(request, "billing-checkout", owner_id)
    if plan is None:
        raise HTTPException(422, "Plano inválido.")
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "O checkout mensal ainda não está configurado.")

    recovering = False
    async with _subscription_checkout_lock(owner_id):
        db = SessionLocal()
        try:
            # A process-local async lock covers SQLite/dev and concurrent calls
            # within one worker. PostgreSQL advisory locking also serializes the
            # reservation across separate Render workers and service instances.
            if db.get_bind().dialect.name == "postgresql":
                db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                    {"lock_key": f"billing-subscription-checkout:{owner_id}"},
                )
            existing = db.scalar(
                select(BillingSubscription)
                .where(BillingSubscription.owner_id == owner_id)
                .order_by(BillingSubscription.updated_at.desc())
                .limit(1)
            )
            if existing and existing.status == "pending" and existing.checkout_url:
                if existing.plan_code != req.plan_code:
                    raise HTTPException(409, "Você tem outro plano aguardando pagamento. Conclua ou cancele esse checkout antes de escolher outro.")
                return {
                    "checkout_url": existing.checkout_url,
                    "external_reference": existing.external_reference,
                    "plan_code": existing.plan_code,
                    "monthly_amount": existing.monthly_amount,
                    "frequency": "monthly",
                }
            if existing and existing.status == "duplicate_review":
                raise HTTPException(409, "O checkout anterior precisa de conferência para evitar uma cobrança duplicada. Entre em contato pelo canal de suporte.")
            if existing and (existing.status in {"authorized", "pending", "paused"} or _subscription_is_entitled(existing)):
                raise HTTPException(409, "Você já tem um plano pago ativo ou uma assinatura em processamento. Consulte Plano e cobrança nas Configurações.")
            if existing and existing.status in {"creating", "checkout_unknown", "recovering"}:
                if existing.plan_code != req.plan_code:
                    raise HTTPException(409, "Há um checkout anterior deste outro plano aguardando confirmação. Tente novamente em um minuto.")
                updated_at = existing.updated_at
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                age_seconds = (utc_now() - updated_at).total_seconds()
                if age_seconds < 60:
                    raise HTTPException(409, "Estamos confirmando o checkout anterior. Aguarde um minuto e tente novamente.")
                recovering = True
                external_reference = existing.external_reference
                subscription_id = existing.id
                existing.status = "recovering"
                existing.updated_at = utc_now()
                db.commit()
            else:
                external_reference = f"subscription-{req.plan_code}-{uuid.uuid4().hex}"
                subscription = BillingSubscription(
                    owner_id=owner_id,
                    plan_code=req.plan_code,
                    external_reference=external_reference,
                    payer_email=email,
                    monthly_amount=int(plan["amount"]),
                    currency="BRL",
                    status="creating",
                )
                db.add(subscription)
                db.commit()
                db.refresh(subscription)
                subscription_id = subscription.id
        finally:
            db.close()

    if recovering:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                search_response = await client.get(
                    "https://api.mercadopago.com/preapproval/search",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": external_reference},
                )
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Ainda não foi possível confirmar o checkout anterior. Tente novamente em instantes.") from exc
        if search_response.status_code >= 400:
            raise HTTPException(503, "Ainda não foi possível confirmar o checkout anterior. Tente novamente em instantes.")
        try:
            search_body = search_response.json()
        except ValueError as exc:
            raise HTTPException(503, "O Mercado Pago retornou uma resposta inválida ao verificar o checkout anterior.") from exc
        if not isinstance(search_body, dict):
            raise HTTPException(503, "O Mercado Pago retornou uma resposta inválida ao verificar o checkout anterior.")
        matches = [
            item for item in (search_body.get("results") or [])
            if isinstance(item, dict) and str(item.get("external_reference") or "") == external_reference
        ]
        if len(matches) > 1:
            db = SessionLocal()
            try:
                current = db.get(BillingSubscription, subscription_id)
                if current:
                    current.status = "duplicate_review"
                    current.updated_at = utc_now()
                    db.commit()
            finally:
                db.close()
            raise HTTPException(409, "O Mercado Pago retornou mais de uma assinatura para este checkout. O sistema bloqueou uma nova cobrança para evitar duplicidade.")
        if matches:
            provider = matches[0]
            provider_id = str(provider.get("id") or "").strip()
            checkout_url = str(provider.get("init_point") or "").strip()
            if not provider_id or not checkout_url:
                raise HTTPException(503, "A assinatura foi encontrada, mas o Mercado Pago ainda não retornou o link. Tente novamente em instantes.")
            recurring = provider.get("auto_recurring") if isinstance(provider.get("auto_recurring"), dict) else {}
            if not _monthly_recurring_matches(recurring, int(plan["amount"])):
                db = SessionLocal()
                try:
                    current = db.get(BillingSubscription, subscription_id)
                    if current:
                        current.status = "duplicate_review"
                        current.updated_at = utc_now()
                        db.commit()
                finally:
                    db.close()
                raise HTTPException(409, "A assinatura localizada não corresponde ao preço mensal do plano. O sistema bloqueou um novo checkout para evitar cobrança incorreta.")
            if not _is_valid_mercadopago_checkout_url(checkout_url):
                raise HTTPException(502, "O Mercado Pago retornou um endereço de checkout inválido.")
            db = SessionLocal()
            try:
                current = db.get(BillingSubscription, subscription_id)
                if current is None:
                    raise HTTPException(500, "Não foi possível recuperar os dados da assinatura.")
                current.mercadopago_preapproval_id = provider_id
                current.checkout_url = checkout_url
                current.status = str(provider.get("status") or "pending").casefold()
                current.next_payment_at = _mp_datetime(provider.get("next_payment_date"))
                current.updated_at = utc_now()
                db.commit()
            finally:
                db.close()
            return {"checkout_url": checkout_url, "external_reference": external_reference, "plan_code": req.plan_code, "monthly_amount": int(plan["amount"]), "frequency": "monthly"}

        db = SessionLocal()
        try:
            current = db.get(BillingSubscription, subscription_id)
            if current:
                current.status = "creating"
                current.updated_at = utc_now()
                db.commit()
        finally:
            db.close()

    base_url = _public_base_url()
    return_path = (
        "/configuracoes?subscription=return#cobranca"
        if req.plan_code == "consultoria"
        else "/dashboard?subscription=return"
    )
    payload = {
        "reason": f"Candidatura Certa — Plano {plan['name']} mensal",
        "external_reference": external_reference,
        "payer_email": email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": int(plan["amount"]) / 100,
            "currency_id": "BRL",
        },
        "back_url": f"{base_url}{return_path}",
        "status": "pending",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.mercadopago.com/preapproval",
                headers={"Authorization": f"Bearer {token}", "X-Idempotency-Key": external_reference},
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.warning("Falha ambígua ao iniciar assinatura Mercado Pago external_reference=%s", external_reference)
        db = SessionLocal()
        try:
            current = db.get(BillingSubscription, subscription_id)
            if current:
                current.status = "checkout_unknown"
                current.updated_at = utc_now()
                db.commit()
        finally:
            db.close()
        raise HTTPException(502, "Não foi possível confirmar se o Mercado Pago criou o checkout. Tente novamente em um minuto; vamos conferir antes de criar outro.") from exc
    if response.status_code >= 400:
        logger.warning("Mercado Pago recusou assinatura status=%s external_reference=%s", response.status_code, external_reference)
        db = SessionLocal()
        try:
            current = db.get(BillingSubscription, subscription_id)
            if current:
                # A 5xx may have been emitted after the provider created the
                # subscription. Keep the durable reference recoverable instead
                # of allowing a fresh preapproval with another reference.
                current.status = "checkout_unknown" if response.status_code >= 500 else "checkout_failed"
                current.updated_at = utc_now()
                db.commit()
        finally:
            db.close()
        if response.status_code >= 500:
            raise HTTPException(502, "O Mercado Pago não confirmou se criou a assinatura. Aguarde um minuto para conferirmos antes de tentar novamente.")
        raise HTTPException(502, "O Mercado Pago recusou a criação da assinatura.")
    try:
        provider = response.json()
    except ValueError as exc:
        db = SessionLocal()
        try:
            current = db.get(BillingSubscription, subscription_id)
            if current:
                current.status = "checkout_unknown"
                current.updated_at = utc_now()
                db.commit()
        finally:
            db.close()
        raise HTTPException(502, "O Mercado Pago retornou uma resposta inválida para a assinatura.") from exc
    provider_id = str(provider.get("id") or "").strip()
    checkout_url = str(provider.get("init_point") or "").strip()
    if not provider_id or not checkout_url:
        db = SessionLocal()
        try:
            current = db.get(BillingSubscription, subscription_id)
            if current:
                current.status = "checkout_unknown"
                current.updated_at = utc_now()
                db.commit()
        finally:
            db.close()
        raise HTTPException(502, "O Mercado Pago não retornou o link da assinatura.")
    if not _is_valid_mercadopago_checkout_url(checkout_url):
        raise HTTPException(502, "O Mercado Pago retornou um endereço de checkout inválido.")

    db = SessionLocal()
    try:
        current = db.get(BillingSubscription, subscription_id)
        if current is None:
            raise HTTPException(500, "Não foi possível salvar os dados da assinatura.")
        current.mercadopago_preapproval_id = provider_id
        current.checkout_url = checkout_url
        current.status = str(provider.get("status") or "pending").casefold()
        current.next_payment_at = _mp_datetime(provider.get("next_payment_date"))
        current.updated_at = utc_now()
        db.commit()
    finally:
        db.close()
    return {
        "checkout_url": checkout_url,
        "external_reference": external_reference,
        "plan_code": req.plan_code,
        "monthly_amount": int(plan["amount"]),
        "frequency": "monthly",
    }


@app.get("/billing/subscription")
def get_current_subscription(user=Depends(authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Login necessário.")
    db = SessionLocal()
    try:
        opportunity_usage = monthly_opportunity_usage(db, owner_id)
        subscription = db.scalar(
            select(BillingSubscription)
            .where(BillingSubscription.owner_id == owner_id)
            .order_by(BillingSubscription.updated_at.desc())
            .limit(1)
        )
        if subscription is None:
            return {
                "plan_code": "essential",
                "plan_name": "Essencial",
                "status": "free",
                "active": False,
                "opportunities": {
                    "used": opportunity_usage["used"],
                    "limit": opportunity_usage["limit"],
                    "remaining": opportunity_usage["remaining"],
                    "resets_at": opportunity_usage["resets_at"].isoformat(),
                },
            }
        plan = SUBSCRIPTION_PLANS.get(subscription.plan_code, {})
        return {
            "plan_code": subscription.plan_code,
            "plan_name": plan.get("name", subscription.plan_code.title()),
            "status": subscription.status,
            "active": _subscription_is_entitled(subscription),
            "monthly_amount": subscription.monthly_amount,
            "currency": subscription.currency,
            "next_payment_at": subscription.next_payment_at.isoformat() if subscription.next_payment_at else None,
            "access_until": subscription.access_until.isoformat() if subscription.access_until else None,
            "can_cancel": bool(subscription.mercadopago_preapproval_id and subscription.status in {"pending", "authorized", "paused"}),
            "opportunities": {
                "used": opportunity_usage["used"],
                "limit": opportunity_usage["limit"],
                "remaining": opportunity_usage["remaining"],
                "resets_at": opportunity_usage["resets_at"].isoformat(),
            },
        }
    finally:
        db.close()


@app.get("/api/documents/{document_id}/download.pdf")
def download_generated_document_pdf(document_id: int, user=Depends(authenticated_user)):
    """Download the same private generated document as a print-ready PDF."""
    owner_id = _require_owner_id(user)
    db = SessionLocal()
    try:
        document = db.scalar(select(GeneratedDocument).where(
            GeneratedDocument.id == document_id,
            GeneratedDocument.owner_id == owner_id,
        ))
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        if _document_expired(document):
            raise HTTPException(410, "Este documento expirou. Gere novamente para renovar o acesso.")
        if not document.content.startswith(b"PK"):
            raise HTTPException(404, "Documento não encontrado.")
        application = _application_for_user(db, document.application_id, user)
        if application is None:
            raise HTTPException(404, "Documento não encontrado.")
        _require_document_export(user, application.id)
        filename = re.sub(r"[^A-Za-z0-9._-]", "-", Path(document.filename).stem)[:150] + ".pdf"
        try:
            content = docx_to_pdf(document.content, title=document.title or filename)
        except Exception as exc:
            logger.exception("Falha ao converter documento para PDF document_id=%s", document.id)
            raise HTTPException(500, "Não foi possível preparar o PDF agora. Baixe a versão DOCX.") from exc
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    finally:
        db.close()


_APPLICATION_EMAIL_PATTERN = re.compile(
    r"(?<![A-Z0-9._%+-])[A-Z0-9._%+-]{1,64}@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+(?![A-Z0-9_%+-])",
    re.IGNORECASE,
)


def _application_recipient_emails(application: Application, user: dict, candidate_email: str = "") -> list[str]:
    """Extract only public addresses explicitly present in this job's text."""
    description = str(application.job.description or "")[:50000]
    own_addresses = {
        str(value or "").strip().casefold()
        for value in (user.get("email"), candidate_email)
        if str(value or "").strip()
    }
    found: list[str] = []
    for match in _APPLICATION_EMAIL_PATTERN.finditer(description):
        address = match.group(0).strip(".,;:!?)]}>\"'").casefold()
        if address not in own_addresses and address not in found:
            found.append(address)
        if len(found) >= 8:
            break
    return found


def _current_application_documents(db, application: Application, user: dict):
    owner_id = str(_owner_id(user) or application.job.owner_id or "").strip()
    if not owner_id:
        raise HTTPException(401, "Entre na sua conta para preparar o envio.")
    delivery = _archive_application_documents(db, application, user)
    if delivery is None:
        raise HTTPException(409, "Gere e libere o currículo e a carta desta vaga antes de enviar por e-mail.")
    documents = db.scalars(select(GeneratedDocument).where(
        GeneratedDocument.owner_id == owner_id,
        GeneratedDocument.application_id == application.id,
        GeneratedDocument.kind.in_(("resume", "cover_letter")),
        GeneratedDocument.version.in_((application.resume_version, application.cover_letter_version)),
    )).all()
    current = {document.kind: document for document in documents}
    resume = current.get("resume")
    letter = current.get("cover_letter")
    if (
        resume is None or letter is None
        or resume.version != application.resume_version
        or letter.version != application.cover_letter_version
        or _document_expired(resume) or _document_expired(letter)
    ):
        raise HTTPException(409, "Os documentos atuais ainda não estão prontos. Gere-os novamente e tente outra vez.")
    return resume, letter


def _application_email_body(application: Application, candidate: Candidate | None) -> str:
    letter = str(application.cover_letter_text or "").strip()
    if not letter:
        raise HTTPException(409, "A carta desta candidatura ainda não foi gerada.")
    name = str(candidate.name if candidate else "").strip()
    signature = f"\n\nAtenciosamente,\n{name}" if name else ""
    return letter + signature


def _application_email_payload(db, application: Application, user: dict, owner_id: str) -> dict[str, Any]:
    _require_document_export(user, application.id)
    candidate = _candidate_for_user(db, user)
    resume, letter = _current_application_documents(db, application, user)
    resume_pdf = docx_to_pdf(resume.content, title=resume.title or "Currículo")
    letter_pdf = docx_to_pdf(letter.content, title=letter.title or "Carta de apresentação")
    if len(resume_pdf) + len(letter_pdf) > 7 * 1024 * 1024:
        raise HTTPException(413, "Os PDFs desta candidatura excedem o limite de anexos do e-mail.")
    recipients = _application_recipient_emails(
        application, user, candidate.email if candidate else ""
    )
    subject = f"Candidatura: {application.job.title or 'Oportunidade'}"
    subject = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", subject).strip()[:180]
    return {
        "application_id": application.id,
        "company": application.job.company,
        "job_title": application.job.title,
        "recipients": recipients,
        "subject": subject,
        "body": _application_email_body(application, candidate),
        "resume_version": application.resume_version,
        "cover_letter_version": application.cover_letter_version,
        "attachments": [
            {"name": re.sub(r"[^A-Za-z0-9._-]", "-", Path(resume.filename).stem)[:140] + ".pdf", "size": len(resume_pdf)},
            {"name": re.sub(r"[^A-Za-z0-9._-]", "-", Path(letter.filename).stem)[:140] + ".pdf", "size": len(letter_pdf)},
        ],
        "_resume_pdf": resume_pdf,
        "_letter_pdf": letter_pdf,
        "smtp_configured": _email_transport_config() is not None,
        "account_email_verified": bool(user.get("email_confirmed_at") or user.get("confirmed_at")),
        "submission_status": None,
    }


@app.get("/applications/{app_id}/email-submission/preview")
def preview_application_email_submission(
    app_id: int,
    user=Depends(authenticated_user),
    request: Request = None,
):
    """Show the destination, content and attachments before the candidate approves sending."""
    owner_id = _require_owner_id(user)
    if request is not None:
        _enforce_rate_limit(request, "application-email-preview", owner_id)
    db = SessionLocal()
    try:
        application = _application_for_user(db, app_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura não encontrada.")
        payload = _application_email_payload(db, application, user, owner_id)
        payload["submission_statuses"] = []
        for recipient in payload["recipients"]:
            recipient_hash = hashlib.sha256(recipient.casefold().encode("utf-8")).hexdigest()
            record = db.scalar(select(EmailApplicationSubmission).where(
                EmailApplicationSubmission.owner_id == owner_id,
                EmailApplicationSubmission.application_id == application.id,
                EmailApplicationSubmission.recipient_hash == recipient_hash,
            ))
            payload["submission_statuses"].append({
                "recipient": recipient,
                "status": record.status if record else None,
                "sent_at": record.sent_at.isoformat() if record and record.sent_at else None,
            "last_error": record.last_error if record else None,
            })
        payload.pop("_resume_pdf", None)
        payload.pop("_letter_pdf", None)
        return payload
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Falha ao preparar prévia de candidatura por e-mail app_id=%s", app_id)
        if isinstance(exc, ValueError):
            raise HTTPException(409, "Não foi possível converter os documentos desta candidatura para PDF.") from exc
        raise
    finally:
        db.close()


@app.post("/applications/{app_id}/email-submission/send")
def send_application_by_email(
    app_id: int,
    req: EmailApplicationSubmissionRequest,
    user=Depends(authenticated_user),
    request: Request = None,
):
    """Send one reviewed application email; repeated submits are deduplicated."""
    owner_id = _require_owner_id(user)
    if request is not None:
        _enforce_rate_limit(request, "application-email-send", owner_id)
    if not req.consent:
        raise HTTPException(400, "Confirme que revisou e autoriza o envio dos documentos ao recrutador.")
    if not (user.get("email_confirmed_at") or user.get("confirmed_at")):
        raise HTTPException(403, "Confirme o e-mail da sua conta antes de enviar candidaturas.")
    recipient = req.recipient.strip().casefold()
    if "\r" in recipient or "\n" in recipient or not _APPLICATION_EMAIL_PATTERN.fullmatch(recipient):
        raise HTTPException(422, "O endereço de e-mail do recrutador é inválido.")
    smtp_config = _email_transport_config()
    if smtp_config is None:
        raise HTTPException(503, "O envio por e-mail está indisponível no momento. Baixe os PDFs pela biblioteca.")
    body = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", req.body).strip()
    if len(body) < 20 or len(body.encode("utf-8")) > 24000:
        raise HTTPException(422, "Revise o texto do e-mail antes de enviar.")

    db = SessionLocal()
    try:
        application = _application_for_user(db, app_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura não encontrada.")
        candidate = _candidate_for_user(db, user)
        if recipient not in _application_recipient_emails(
            application, user, candidate.email if candidate else ""
        ):
            raise HTTPException(422, "Escolha um endereço que apareça no anúncio da vaga.")
        _refresh_application_risk(application)
        _enforce_application_risk_gate(application, "CANDIDATURA_ENVIADA")
        preview = _application_email_payload(db, application, user, owner_id)
        if (
            req.resume_version != application.resume_version
            or req.cover_letter_version != application.cover_letter_version
        ):
            raise HTTPException(409, "Os documentos mudaram desde a prévia. Atualize e revise o envio novamente.")
        resume, letter = _current_application_documents(db, application, user)
        resume_pdf = preview.pop("_resume_pdf")
        letter_pdf = preview.pop("_letter_pdf")
        if len(resume_pdf) + len(letter_pdf) > 7 * 1024 * 1024:
            raise HTTPException(413, "Os PDFs desta candidatura excedem o limite de anexos do e-mail.")

        safe_company = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", application.job.company or "Empresa")[:160]
        safe_title = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", application.job.title or "Oportunidade")[:160]
        message = EmailMessage()
        message["Subject"] = f"Candidatura: {safe_title} - {safe_company}"[:190]
        message["From"] = str(smtp_config["sender"])
        message["To"] = recipient
        reply_to = str(user.get("email") or "").strip()
        if _APPLICATION_EMAIL_PATTERN.fullmatch(reply_to):
            message["Reply-To"] = reply_to
        message.set_content(body)
        resume_name = re.sub(r"[^A-Za-z0-9._-]", "-", Path(resume.filename).stem)[:140] + ".pdf"
        letter_name = re.sub(r"[^A-Za-z0-9._-]", "-", Path(letter.filename).stem)[:140] + ".pdf"
        message.add_attachment(resume_pdf, maintype="application", subtype="pdf", filename=resume_name)
        message.add_attachment(letter_pdf, maintype="application", subtype="pdf", filename=letter_name)

        recipient_hash = hashlib.sha256(recipient.encode("utf-8")).hexdigest()
        submission = db.scalar(select(EmailApplicationSubmission).where(
            EmailApplicationSubmission.owner_id == owner_id,
            EmailApplicationSubmission.application_id == application.id,
            EmailApplicationSubmission.recipient_hash == recipient_hash,
        ).with_for_update())
        if submission is not None and submission.status in {"SENT", "SENDING", "UNKNOWN"}:
            raise HTTPException(409, "Este envio já foi iniciado. Confira o histórico antes de tentar novamente.")
        if submission is not None and submission.attempt_count >= 3:
            raise HTTPException(429, "O limite de tentativas para este destino foi atingido.")
        now = utc_now()
        if submission is None:
            submission = EmailApplicationSubmission(
                owner_id=owner_id,
                application_id=application.id,
                recipient_hash=recipient_hash,
                resume_version=application.resume_version,
                cover_letter_version=application.cover_letter_version,
                status="SENDING",
                attempt_count=1,
                consented_at=now,
                started_at=now,
            )
            db.add(submission)
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(409, "Outro envio para este destino já foi iniciado.") from exc
        else:
            submission.status = "SENDING"
            submission.attempt_count += 1
            submission.consented_at = now
            submission.started_at = now
            submission.resume_version = application.resume_version
            submission.cover_letter_version = application.cover_letter_version
            submission.last_error = None
        submission_id = submission.id
        db.commit()

        send_invoked = False
        try:
            _send_email_message(message, smtp_config, timeout=15)
            send_invoked = True
        except (OSError, smtplib.SMTPException, TimeoutError, httpx.HTTPError, ValueError, RuntimeError):
            current = db.get(EmailApplicationSubmission, submission_id)
            if current is not None:
                current.status = "UNKNOWN" if send_invoked else "FAILED"
                current.last_error = (
                    "O servidor não confirmou se recebeu a mensagem; confira o e-mail enviado antes de agir."
                    if send_invoked else "O servidor recusou a conexão antes do envio; você pode tentar novamente."
                )
                db.commit()
            return {
                "status": "UNKNOWN" if send_invoked else "FAILED",
                "message": (
                    "O servidor não confirmou o resultado. Confira a pasta de enviados antes de fazer qualquer novo envio."
                    if send_invoked else "O serviço de e-mail recusou a conexão; nenhum envio foi confirmado. Você pode tentar novamente."
                ),
            }

        current = db.get(EmailApplicationSubmission, submission_id)
        if current is None:
            raise HTTPException(500, "O e-mail foi enviado, mas o registro de confirmação não pôde ser recuperado.")
        current.status = "SENT"
        current.sent_at = utc_now()
        current.last_error = None
        _add_event(
            db,
            application,
            "CANDIDATURA_ENVIADA",
            "Candidatura enviada por e-mail após revisão e autorização do candidato.",
            channel="email",
        )
        db.commit()
        return {"status": "SENT", "message": "Candidatura enviada. O envio foi registrado no histórico."}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Falha ao enviar candidatura por e-mail app_id=%s", app_id)
        raise HTTPException(500, "Não foi possível concluir o envio por e-mail.")
    finally:
        db.close()


def _cleanup_expiration_email_outbox() -> int:
    db = SessionLocal()
    try:
        return cleanup_expiration_email_outbox(db)
    finally:
        db.close()


def _current_consultation_credit(db, subscription: BillingSubscription, owner_id: str) -> ConsultationCredit | None:
    now = utc_now()
    credits = db.scalars(
        select(ConsultationCredit)
        .where(
            ConsultationCredit.subscription_id == subscription.id,
            ConsultationCredit.owner_id == owner_id,
            ConsultationCredit.booking_status.in_(("available", "requested")),
        )
        .order_by(ConsultationCredit.period_end.desc(), ConsultationCredit.id.desc())
    ).all()
    for credit in credits:
        period_end = credit.period_end
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end > now:
            return credit
    return None


@app.get("/billing/consultation/session")
def get_consultation_session(user=Depends(authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Login necessário.")
    db = SessionLocal()
    try:
        subscription = db.scalar(
            select(BillingSubscription)
            .where(BillingSubscription.owner_id == owner_id)
            .order_by(BillingSubscription.updated_at.desc())
            .limit(1)
        )
        if subscription is None or subscription.plan_code != "consultoria":
            return {"eligible": False, "state": "not_included"}
        if not _subscription_is_entitled(subscription):
            state = "awaiting_payment" if subscription.status in {"pending", "authorized"} else "inactive"
            return {"eligible": False, "state": state}
        credit = _current_consultation_credit(db, subscription, owner_id)
        if credit is None:
            return {"eligible": True, "state": "awaiting_payment"}
        result = {
            "eligible": True,
            "state": credit.booking_status,
            "period_end": credit.period_end.isoformat(),
        }
        if credit.booking_status == "requested" and credit.booking_reference:
            result["booking_reference"] = credit.booking_reference
            result["whatsapp_url"] = _consultation_whatsapp_url(credit.booking_reference)
        return result
    finally:
        db.close()


@app.post("/billing/consultation/session/request")
def request_consultation_session(
    req: ConsultationBookingRequest,
    request: Request,
    user=Depends(authenticated_user),
):
    owner_id = str(_owner_id(user) or "").strip()
    if not owner_id:
        raise HTTPException(401, "Login necessário.")
    _enforce_rate_limit(request, "consultation-booking", owner_id)
    availability = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", req.availability)).strip()
    if len(availability) < 5:
        raise HTTPException(422, "Informe alguns dias ou horários para o atendimento.")
    db = SessionLocal()
    try:
        subscription = db.scalar(
            select(BillingSubscription)
            .where(BillingSubscription.owner_id == owner_id)
            .order_by(BillingSubscription.updated_at.desc())
            .limit(1)
        )
        if subscription is None or subscription.plan_code != "consultoria":
            raise HTTPException(403, "O agendamento mensal está incluído no plano Consultoria.")
        if not _subscription_is_entitled(subscription):
            raise HTTPException(409, "A assinatura Consultoria não tem um ciclo pago ativo.")
        credit = _current_consultation_credit(db, subscription, owner_id)
        if credit is None:
            raise HTTPException(409, "O Mercado Pago ainda não confirmou o pagamento deste ciclo. Atualize esta página em instantes.")
        if credit.booking_status == "available":
            credit.booking_status = "requested"
            credit.booking_reference = f"CC-{uuid.uuid4().hex[:8].upper()}"
            credit.booking_requested_at = utc_now()
            credit.updated_at = utc_now()
            db.commit()
        reference = credit.booking_reference
        if not reference:
            raise HTTPException(409, "Este atendimento precisa de conferência. Fale com o suporte da Consultoria.")
        return {
            "state": "requested",
            "booking_reference": reference,
            "whatsapp_url": _consultation_whatsapp_url(reference, availability),
            "message": "Sua solicitação está pronta. Envie a mensagem no WhatsApp para combinar o horário.",
        }
    finally:
        db.close()


@app.post("/billing/subscription/cancel")
async def cancel_current_subscription(user=Depends(authenticated_user)):
    owner_id = str(_owner_id(user) or "").strip()
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not owner_id:
        raise HTTPException(401, "Login necessário.")
    if not token:
        raise HTTPException(503, "O gerenciamento de assinaturas está indisponível.")
    db = SessionLocal()
    try:
        subscription = db.scalar(
            select(BillingSubscription)
            .where(BillingSubscription.owner_id == owner_id)
            .order_by(BillingSubscription.updated_at.desc())
            .limit(1)
        )
        if subscription is None or not subscription.mercadopago_preapproval_id:
            raise HTTPException(404, "Nenhuma assinatura recorrente foi encontrada.")
        if subscription.status == "canceled":
            return {"canceled": True, "access_until": subscription.access_until.isoformat() if subscription.access_until else None}
        provider_id = subscription.mercadopago_preapproval_id
        subscription_id = subscription.id
    finally:
        db.close()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.put(
                f"https://api.mercadopago.com/preapproval/{provider_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"status": "canceled"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Falha ao cancelar assinatura Mercado Pago preapproval_id=%s", provider_id)
        raise HTTPException(502, "Não foi possível cancelar a renovação agora. Tente novamente.") from exc
    if response.status_code >= 400:
        logger.warning("Mercado Pago recusou cancelamento status=%s preapproval_id=%s", response.status_code, provider_id)
        raise HTTPException(502, "O Mercado Pago não confirmou o cancelamento. Tente novamente.")
    try:
        provider = response.json()
    except ValueError as exc:
        raise HTTPException(502, "O Mercado Pago não confirmou o cancelamento. Tente novamente.") from exc
    db = SessionLocal()
    try:
        subscription = db.get(BillingSubscription, subscription_id)
        if subscription is None:
            raise HTTPException(404, "Assinatura não encontrada.")
        remote_status = str(provider.get("status") or "").casefold()
        if remote_status not in {"canceled", "cancelled"}:
            raise HTTPException(502, "O Mercado Pago ainda não confirmou o cancelamento. Tente novamente.")
        subscription.status = "canceled"
        if provider.get("next_payment_date"):
            subscription.next_payment_at = _mp_datetime(provider.get("next_payment_date"))
        # access_until was set only after a confirmed recurring payment.
        subscription.updated_at = utc_now()
        db.commit()
        return {
            "canceled": True,
            "status": "canceled",
            "access_until": subscription.access_until.isoformat() if subscription.access_until else None,
            "message": "Renovação cancelada. O acesso continua até o fim do período já pago.",
        }
    finally:
        db.close()


@app.get("/billing/ebook/hackeando-disc", include_in_schema=False)
def download_pro_ebook(user=Depends(authenticated_user)):
    offer = _document_export_metadata(user)
    allowed = offer.get("plan") == "pro" and offer.get("allowed") is True
    owner_id = _owner_id(user)
    if owner_id:
        db = SessionLocal()
        try:
            subscription = db.scalar(
                select(BillingSubscription)
                .where(BillingSubscription.owner_id == owner_id)
                .order_by(BillingSubscription.updated_at.desc())
                .limit(1)
            )
            allowed = allowed or (
                subscription is not None
                and subscription.plan_code in {"pro", "consultoria"}
                and _subscription_is_entitled(subscription)
            )
        finally:
            db.close()
    if not allowed:
        raise HTTPException(403, "O e-book Hackeando o DISC está incluído nos planos Pro e Consultoria ativos.")
    if not PRO_BOOK_PATH.is_file():
        logger.error("Arquivo do e-book Pro não está disponível no deploy.")
        raise HTTPException(503, "O e-book ainda não está disponível para download. Tente novamente mais tarde.")
    return FileResponse(
        PRO_BOOK_PATH,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="Hackeando-DISC.docx",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/billing/document-export/checkout")
async def create_document_export_checkout(req: DocumentExportCheckoutRequest, request: Request, user=Depends(authenticated_user)):
    owner_id = _owner_id(user)
    if not owner_id:
        raise HTTPException(409, "Login necessário para iniciar o pagamento.")
    _enforce_rate_limit(request, "billing-checkout", str(owner_id))
    mercadopago_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not mercadopago_token:
        raise HTTPException(503, "Checkout Mercado Pago ainda não está configurado.")
    price_cents = _document_export_price_cents()
    order_nsu = f"export-{uuid.uuid4().hex}"
    base_url = _public_base_url()
    return_url = f"{base_url}/billing/mercadopago/success?application_id={req.application_id}&order_nsu={quote(order_nsu, safe='')}"
    payload = {
        "items": [{"id": "document-export", "title": "Exportação de currículo e carta personalizada", "quantity": 1, "currency_id": "BRL", "unit_price": price_cents / 100}],
        "external_reference": order_nsu,
        "payer": {"email": str(user.get("email") or "")},
        "back_urls": {
            "success": f"{return_url}&return_status=approved",
            "pending": f"{return_url}&return_status=pending",
            "failure": f"{return_url}&return_status=failure",
        },
        "auto_return": "approved",
        "notification_url": f"{base_url}/webhooks/mercadopago",
    }
    db = SessionLocal()
    try:
        application = _application_for_user(db, req.application_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        db.add(DocumentExportPurchase(
            owner_id=owner_id,
            application_id=application.id,
            payer_email=str(user.get("email") or "").strip(),
            payer_email_confirmed=bool(user.get("email_confirmed_at") or user.get("confirmed_at")),
            order_nsu=order_nsu,
            amount=price_cents,
        ))
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
    """Verify Mercado Pago payment and recurring-subscription notifications."""
    _enforce_rate_limit(request, "mercadopago-webhook")
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        # A webhook without the server-to-server credential cannot be verified
        # safely. Surface the deployment/configuration error instead of
        # acknowledging the event as if it had been processed.
        raise HTTPException(503, "Integração Mercado Pago indisponível.")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not _mercadopago_signature_is_valid(request, payload):
        raise HTTPException(401, "Webhook Mercado Pago não autorizado.")
    payment_id = str((payload.get("data") or {}).get("id") or payload.get("id") or request.query_params.get("data.id") or "").strip()
    notification_type = str(payload.get("type") or payload.get("topic") or "").strip().casefold()
    if not payment_id:
        return {"received": True, "verified": False}

    resource_url = None
    if notification_type in {"subscription_preapproval", "preapproval"}:
        resource_url = f"https://api.mercadopago.com/preapproval/{payment_id}"
    elif notification_type == "subscription_authorized_payment":
        resource_url = f"https://api.mercadopago.com/authorized_payments/{payment_id}"
    elif notification_type in {"payment", "payments", ""}:
        resource_url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    else:
        return {"received": True, "verified": False}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                resource_url,
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

    if notification_type in {"subscription_preapproval", "preapproval"}:
        db = SessionLocal()
        try:
            subscription = _sync_subscription_from_provider(db, payment)
            return {
                "received": True,
                "verified": subscription is not None,
                "subscription_status": subscription.status if subscription else None,
                "plan_code": subscription.plan_code if subscription else None,
            }
        finally:
            db.close()

    if notification_type == "subscription_authorized_payment":
        invoice = payment
        invoice_payment = invoice.get("payment") if isinstance(invoice.get("payment"), dict) else {}
        invoice_payment_status = str(invoice_payment.get("status") or "").casefold()
        invoice_summary = str(invoice.get("summarized") or "").casefold()
        payment_id = str(invoice_payment.get("id") or payment_id)
        payment = {
            "id": payment_id,
            "preapproval_id": invoice.get("preapproval_id"),
            "status": invoice_payment_status or ("approved" if invoice_summary in {"paid", "approved"} else invoice_summary),
            "transaction_amount": invoice.get("transaction_amount"),
            "currency_id": invoice.get("currency_id"),
        }

    preapproval_id = str(payment.get("preapproval_id") or "").strip()
    if preapproval_id:
        try:
            amount = int(round(float(payment.get("transaction_amount") or 0) * 100))
        except (TypeError, ValueError):
            amount = 0
        currency = str(payment.get("currency_id") or "").strip().upper()
        payment_status = str(payment.get("status") or "").strip().casefold()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                subscription_response = await client.get(
                    f"https://api.mercadopago.com/preapproval/{preapproval_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError:
            logger.warning("Falha ao consultar assinatura Mercado Pago preapproval_id=%s", preapproval_id)
            return {"received": True, "verified": False}
        if subscription_response.status_code >= 400:
            logger.warning("Mercado Pago retornou status=%s ao consultar assinatura id=%s", subscription_response.status_code, preapproval_id)
            return {"received": True, "verified": False}
        try:
            provider_subscription = subscription_response.json()
        except ValueError:
            return {"received": True, "verified": False}
        db = SessionLocal()
        try:
            subscription = _sync_subscription_from_provider(db, provider_subscription)
            if subscription is None or subscription.mercadopago_preapproval_id != preapproval_id:
                return {"received": True, "verified": False}
            previous_payment_id = subscription.last_payment_id
            is_replay = previous_payment_id == payment_id and subscription.last_payment_status == payment_status
            if is_replay:
                return {
                    "received": True,
                    "verified": True,
                    "idempotent": True,
                    "subscription_status": subscription.status,
                    "payment_status": payment_status,
                    "entitled": _subscription_is_entitled(subscription),
                }
            subscription.last_payment_id = payment_id
            expected_amount = int(subscription.monthly_amount)
            amount_matches = amount == expected_amount and currency == "BRL"
            subscription.last_payment_status = payment_status if amount_matches else "amount_mismatch"
            if amount_matches and payment_status == "approved" and subscription.status in {"authorized", "canceled"}:
                paid_through = _mp_datetime(provider_subscription.get("next_payment_date"))
                current_access_until = subscription.access_until
                if current_access_until and current_access_until.tzinfo is None:
                    current_access_until = current_access_until.replace(tzinfo=timezone.utc)
                if paid_through is not None and (current_access_until is None or paid_through > current_access_until):
                    period_start = current_access_until or utc_now()
                    subscription.access_until = paid_through
                    _ensure_consultation_credit(
                        db,
                        subscription,
                        payment_id,
                        period_start,
                        paid_through,
                    )
            elif amount_matches and payment_status in {"refunded", "charged_back"} and previous_payment_id == payment_id:
                subscription.access_until = utc_now()
                if subscription.plan_code == "consultoria":
                    credit = db.scalar(
                        select(ConsultationCredit).where(ConsultationCredit.payment_id == payment_id)
                    )
                    if credit is not None:
                        credit.booking_status = "revoked"
                        credit.updated_at = utc_now()
            subscription.updated_at = utc_now()
            db.commit()
            return {
                "received": True,
                "verified": amount_matches,
                "idempotent": is_replay,
                "subscription_status": subscription.status,
                "payment_status": payment_status,
                "entitled": _subscription_is_entitled(subscription),
            }
        finally:
            db.close()

    order_nsu = str(payment.get("external_reference") or "").strip()
    if not order_nsu:
        return {"received": True, "verified": False}
    if str(payment.get("currency_id") or "").strip().upper() != "BRL":
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
            if outcome in {"paid", "idempotent"} and _purchase_generation_wakeup is not None:
                _purchase_generation_wakeup.set()
            receipt = _send_purchase_receipt(db, purchase) if outcome in {"paid", "idempotent"} else "not_sent"
            return {
                "received": True,
                "verified": outcome in {"paid", "idempotent"},
                "idempotent": outcome == "idempotent",
                "status": payment.get("status"),
                "receipt": receipt,
            }
        return {"received": True, "verified": bool(purchase), "status": payment.get("status")}
    finally:
        db.close()


@app.get("/billing/mercadopago/success", include_in_schema=False)
def mercadopago_success(request: Request):
    """Return from Mercado Pago directly to the document studio.

    The webhook remains the source of truth for payment approval and queues
    document generation on the server. The browser carries only the linked
    application id and display status; it can poll for completion, but closing
    the browser does not interrupt generation or archival.
    """
    application_id = str(request.query_params.get("application_id") or "").strip()
    if not application_id.isdigit():
        application_id = ""
    provider_status = str(
        request.query_params.get("status")
        or request.query_params.get("collection_status")
        or request.query_params.get("return_status")
        or "pending"
    ).strip().casefold()
    if provider_status in {"approved", "paid"}:
        payment_status = "approved"
    elif provider_status in {"rejected", "failure", "cancelled", "canceled"}:
        payment_status = "failure"
    else:
        payment_status = "pending"
    target = "/criar-documentos"
    params = []
    if application_id:
        params.append(f"application_id={quote(application_id, safe='')}")
    params.append(f"payment_status={payment_status}")
    return RedirectResponse(f"{target}?{'&'.join(params)}", status_code=303)


@app.get("/billing/document-export/status")
def document_export_status(application_id: int, user=Depends(authenticated_user)):
    """Return only this account's latest one-time purchase generation state."""
    owner_id = _require_owner_id(user)
    db = SessionLocal()
    try:
        application = _application_for_user(db, application_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        purchase = db.scalar(
            select(DocumentExportPurchase)
            .where(
                DocumentExportPurchase.owner_id == owner_id,
                DocumentExportPurchase.application_id == application_id,
            )
            .order_by(DocumentExportPurchase.id.desc())
            .limit(1)
        )
        if purchase is None:
            offer = _document_export_metadata(user, application_id)
            return {
                "purchase_status": "NONE",
                "generation_status": "NOT_APPLICABLE",
                "entitlement_source": "plan" if offer.get("allowed") else "none",
                "application_id": application_id,
                "message": "Exportação completa disponível pelo seu plano." if offer.get("allowed") else "Nenhuma compra encontrada.",
            }
        payload = _purchase_generation_payload(purchase)
        payload["entitlement_source"] = "one_time_purchase"
        if payload["generation_status"] == "READY":
            payload["resume_url"] = f"/applications/{application_id}/document"
            payload["letter_url"] = f"/applications/{application_id}/cover-letter/document"
        return payload
    finally:
        db.close()


@app.get("/applications/{app_id}/document", response_class=FileResponse)
def download_doc(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        _require_document_export(user, app.id)
        if not app.document_path: raise HTTPException(404, "Nao possui curriculo gerado.")
        try:
            path = resolve_document_path(app.document_path)
        except ValueError as exc:
            raise HTTPException(404, "Arquivo nao encontrado.") from exc
        if not path.is_file(): raise HTTPException(404, "Arquivo nao encontrado.")
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.patch("/applications/{app_id}/status")
def update_app_status(app_id: int, req: ApplicationStatusRequest, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        if req.status in {"CANDIDATURA_ENVIADA", "ENTREVISTA", "APROVADO"}:
            _refresh_application_risk(app)
            db.commit()
            db.refresh(app)
        db.refresh(app, with_for_update=True)
        previous_status = app.status
        _enforce_application_risk_gate(app, req.status)
        event = None
        if app.status != req.status or req.note or req.channel or req.external_result:
            event = _add_event(db, app, req.status, req.note, req.channel, req.external_result)
        if event is not None and previous_status != "ENTREVISTA" and req.status == "ENTREVISTA":
            db.flush()
            candidate = _candidate_for_user(db, user)
            try:
                candidate_preferences = json.loads(candidate.preferences_data or "{}") if candidate else {}
            except (TypeError, ValueError):
                candidate_preferences = {}
            preferences = normalize_preferences(candidate_preferences)
            enqueue_interview_notification(
                db,
                str(_owner_id(user) or ""),
                app.id,
                event.id,
                preferences["notification_frequency"],
                now=utc_now(),
            )
        db.commit(); db.refresh(app)
        allowed = _document_export_metadata(user)["allowed"]
        return _serialize_app(app, allowed, allowed)
    finally: db.close()

@app.post("/applications/{app_id}/risk-review")
def review_application_risk(app_id: int, user=Depends(authenticated_user)):
    """Registra revisão deliberada para anúncio de qualidade duvidosa ou suspeita."""
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        _refresh_application_risk(app)
        db.commit()
        db.refresh(app)
        if app.fraud_suspected:
            raise HTTPException(409, "Sinais de fraude foram detectados; esta vaga nao pode avancar.")
        if (app.health_band or "").strip().upper() not in {"DUVIDOSA", "SUSPEITA"}:
            raise HTTPException(409, "Esta vaga nao exige confirmacao adicional de risco.")
        app.risk_reviewed_at = utc_now()
        _add_event(db, app, app.status, "Sinais de risco revisados antes de avancar na candidatura.")
        db.commit(); db.refresh(app)
        allowed = _document_export_metadata(user)["allowed"]
        return _serialize_app(app, allowed, allowed)
    finally:
        db.close()

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
def create_cover_letter(job_id: int, user=Depends(authenticated_user), request: Request = None):
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
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
        app.cover_letter_version = _content_version("carta", letter)
        db.commit(); db.refresh(app)
        export = _document_export_metadata(user, app.id)
        return {"job_id": job.id, "application_id": app.id, "company": job.company, "job_title": job.title, "candidate": arts["profile"]["name"], "analysis_score": arts["analysis"]["score"], "personalization_score": arts["personalization"]["personalization_score"], "letter": letter if export["allowed"] else _cover_letter_preview(letter), "preview": not export["allowed"], "export": export, "notice": "Prévia gratuita. A carta completa está incluída no Start e no Pro, ou pode ser comprada à parte." if not export["allowed"] else "Carta completa liberada."}
    finally: db.close()

@app.post("/jobs/{job_id}/cover-letter/document", response_class=FileResponse)
def create_cover_letter_doc(job_id: int, user=Depends(authenticated_user), request: Request = None):
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga nao encontrada.")
        c = _candidate_for_user(db, user)
        app = _ensure_app(db, job, c)
        _require_document_export(user, app.id)
        arts = _build_application(job, c)
        letter = generate_cover_letter(job_title=job.title, company=job.company, profile=arts["profile"], analysis=arts["analysis"], personalization=arts["personalization"])
        path = Path(generate_cover_letter_docx(letter=letter, company=job.company, job_title=job.title)).resolve()
        if not path.is_file(): raise HTTPException(500, "Carta nao foi criada.")
        _save_analysis(app, arts["analysis"], c)
        app.cover_letter_text = letter
        app.cover_letter_path = str(path)
        app.cover_letter_version = _content_version("carta", letter)
        _add_event(db, app, app.status, "Carta de apresentacao gerada.")
        delivery = _archive_application_documents(db, app, user)
        db.commit()
        if delivery is not None:
            _send_document_delivery(db, delivery, user)
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.get("/applications/{app_id}/cover-letter/document", response_class=FileResponse)
def download_cover_letter(app_id: int, user=Depends(authenticated_user)):
    db = SessionLocal()
    try:
        app = _application_for_user(db, app_id, user)
        if app is None: raise HTTPException(404, "Candidatura nao encontrada.")
        _require_document_export(user, app.id)
        if not app.cover_letter_path: raise HTTPException(404, "Nao possui carta gerada.")
        try:
            path = resolve_document_path(app.cover_letter_path)
        except ValueError as exc:
            raise HTTPException(404, "Arquivo nao encontrado.") from exc
        if not path.is_file(): raise HTTPException(404, "Arquivo nao encontrado.")
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)
    finally: db.close()

@app.post("/jobs/{job_id}/generate-document")
def generate_doc(job_id: int, user=Depends(authenticated_user), request: Request = None):
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
    db = SessionLocal()
    try:
        job = _job_for_user(db, job_id, user)
        if job is None: raise HTTPException(404, "Vaga não encontrada.")
        c = _candidate_for_user(db, user)
        arts = _build_application(job, c)
        app = _ensure_app(db, job, c)
        if not _document_export_metadata(user, app.id)["allowed"]:
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
                "export": document_export_offer(user=user),
            }
        path = Path(generate_docx(arts["resume"])).resolve()
        if not path.is_file(): raise HTTPException(500, "Documento nao foi criado.")
        _save_analysis(app, arts["analysis"], c)
        app.personalization_score = arts["personalization"]["personalization_score"]
        app.document_path = str(path)
        app.resume_version = _content_version("cv", arts["resume"])
        _advance_app(db, app, "CURRICULO_GERADO", "Curriculo personalizado gerado.")
        delivery = _archive_application_documents(db, app, user)
        db.commit()
        if delivery is not None:
            _send_document_delivery(db, delivery, user)
        return FileResponse(path=path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name, headers={"X-Application-Id": str(app.id), "X-Application-Status": app.status, "X-Analysis-Score": str(arts["analysis"]["score"]), "X-Personalization-Score": str(arts["personalization"]["personalization_score"])})
    finally: db.close()

@app.post("/document-studio/generate")
def generate_document_studio(req: DocumentStudioRequest, user=Depends(authenticated_user), request: Request = None):
    """Create a tailored resume and cover letter from a role pasted by the user.

    The role is saved as a private opportunity so the existing preview, payment,
    export and application tracking flows can be reused consistently.
    """
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
    db = SessionLocal()
    try:
        candidate = _candidate_for_user(db, user)
        profile = _candidate_profile(candidate)
        linked_application = None
        if req.application_id is not None:
            linked_application = _application_for_user(db, req.application_id, user)
            if linked_application is None:
                raise HTTPException(404, "Vaga vinculada não encontrada.")
        title = req.title.strip()
        company = req.company.strip() or "Empresa não informada"
        description = req.details.strip()
        if linked_application is not None:
            # Reuse the captured opportunity so a document preview never creates
            # a duplicate job/application just because the user opened the studio.
            job = linked_application.job
            job.title = title
            job.company = company
            job.location = req.location.strip()
            job.url = req.url.strip()
            job.description = description
            app_record = linked_application
        else:
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
        app_record.resume_version = _content_version("cv", arts["resume"])
        app_record.cover_letter_text = generate_cover_letter(
            job_title=title,
            company=company,
            profile=arts["profile"],
            analysis=arts["analysis"],
            personalization=arts["personalization"],
        )
        app_record.cover_letter_version = _content_version("carta", app_record.cover_letter_text)
        _advance_app(db, app_record, "ANALISADA", "Documento personalizado criado no Criador de documentos.")
        db.commit()
        db.refresh(job)
        db.refresh(app_record)
        export = _document_export_metadata(user, app_record.id)
        return {
            "status": "PREVIA_GERADA",
            "job_id": job.id,
            "application_id": app_record.id,
            "linked_application": linked_application is not None,
            "company": company,
            "job_title": title,
            "analysis": arts["analysis"],
            "resume_preview": _resume_preview(arts),
            "cover_letter_preview": _cover_letter_preview(app_record.cover_letter_text),
            "quick_copy": {
                "headline": str(arts["profile"].get("headline") or title).strip(),
                "summary": str(arts["profile"].get("summary") or "").strip(),
                "skills": ", ".join(str(value).strip() for value in arts["profile"].get("skills", []) if str(value).strip()),
                "experience": "\n\n".join(
                    " · ".join(str(value).strip() for value in (
                        item.get("role"), item.get("company"), item.get("period"), item.get("description")
                    ) if str(value or "").strip())
                    for item in arts["profile"].get("experiences", [])
                    if isinstance(item, dict)
                ),
                "education": "\n".join(
                    " · ".join(str(value).strip() for value in (
                        item.get("course") or item.get("title"), item.get("institution"), item.get("period")
                    ) if str(value or "").strip())
                    for item in arts["profile"].get("education", [])
                    if isinstance(item, dict)
                ),
            },
            "export": export,
            "notice": "Prévia adaptada ao cargo. Os arquivos completos estão incluídos no Start e no Pro, ou podem ser comprados à parte.",
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

@app.post("/document-studio/export")
def export_document_studio(req: DocumentStudioExportRequest, user=Depends(authenticated_user), request: Request = None):
    """Recover a paid document pair, or generate it for an entitled plan user."""
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
    owner_id = _require_owner_id(user)
    db = SessionLocal()
    try:
        application = _application_for_user(db, req.application_id, user)
        if application is None:
            raise HTTPException(404, "Candidatura nao encontrada.")
        _require_document_export(user, application.id)
        paid_purchase = db.scalar(
            select(DocumentExportPurchase)
            .where(
                DocumentExportPurchase.owner_id == owner_id,
                DocumentExportPurchase.application_id == application.id,
                DocumentExportPurchase.status == "PAID",
            )
            .order_by(DocumentExportPurchase.id.desc())
            .limit(1)
        )
        if paid_purchase is not None:
            claim_status, claimed_id = _claim_paid_document_purchase(
                purchase_id=paid_purchase.id,
                owner_id=owner_id,
                application_id=application.id,
                allow_failed=True,
            )
            if claim_status == "claimed" and claimed_id is not None:
                result = _finish_paid_document_purchase(claimed_id)
            elif claim_status == "ready":
                result = {
                    "generation_status": "READY",
                    "application_id": application.id,
                    "job_id": application.job_id,
                    "resume_url": f"/applications/{application.id}/document",
                    "letter_url": f"/applications/{application.id}/cover-letter/document",
                    "message": "Currículo e carta prontos para baixar.",
                }
            else:
                result = {
                    "generation_status": "PROCESSING" if claim_status in {"processing", "not_claimed"} else "WAITING",
                    "application_id": application.id,
                    "job_id": application.job_id,
                    "message": "Pagamento confirmado. A geração automática está em andamento.",
                }
            if result.get("generation_status") == "READY":
                result["status"] = "DOCUMENTOS_GERADOS"
            elif result.get("generation_status") == "FAILED":
                result["status"] = "DOCUMENTOS_FALHARAM"
            else:
                result["status"] = "DOCUMENTOS_PENDENTES"
            return result

        # Start/Pro subscriptions have no one-time purchase row; preserve the
        # existing on-demand export path while sharing the same safe generator.
        application, delivery = _generate_and_archive_application_documents(
            db,
            application=application,
            owner_id=owner_id,
            user=user,
        )
        db.commit()
        db.refresh(delivery)
        try:
            email_status = _send_document_delivery(db, delivery, user)
            db.refresh(delivery)
        except Exception as exc:
            logger.warning("Falha não bloqueante ao enviar documentos da candidatura id=%s tipo=%s", application.id, type(exc).__name__)
            email_status = "failed"
        return {
            "status": "DOCUMENTOS_GERADOS",
            "application_id": application.id,
            "job_id": application.job_id,
            "resume_url": f"/applications/{application.id}/document",
            "letter_url": f"/applications/{application.id}/cover-letter/document",
            "delivery_id": delivery.id,
            "email_status": delivery.status,
            "email_message": delivery.last_error or (
                "Currículo e carta enviados para o e-mail confirmado da conta."
                if email_status == "sent"
                else "Currículo e carta estão disponíveis na biblioteca de documentos."
            ),
            "message": "Pagamento confirmado. Currículo e carta gerados e salvos na biblioteca.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Falha ao exportar documentos pagos no studio")
        raise HTTPException(500, "Não foi possível gerar os documentos agora.")
    finally:
        db.close()

@app.post("/generate-document")
def generate_doc_standalone(req: ResumeRequest, user=Depends(authenticated_user), request: Request = None):
    if request is not None:
        _enforce_rate_limit(request, "document-generation", str(_owner_id(user) or ""))
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

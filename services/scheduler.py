"""Rotinas assíncronas de coleta, alertas e limpeza de vagas."""

import asyncio
import json
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import and_, delete, or_, select

from app.database import (
    SessionLocal,
    limpar_vagas_expiradas,
    obter_matches_pendentes,
    registrar_alerta_enviado,
    salvar_vagas_em_lote,
)
from app.models import Candidate, EmailIntegration, JobIngestionRun, utc_now
from app.gmail_monitor import sync_all_integrations as sync_all_gmail_integrations
from app.outlook_monitor import sync_all_integrations as sync_all_outlook_integrations
from scrapers.job_collector import coletar_todas_as_fontes


TERMOS_MONITORADOS = [
    "desenvolvedor",
    "programador",
    "analista",
    "estágio",
    "assistente administrativo",
    "atendente",
    "recepcionista",
    "comercial",
]

scheduler = AsyncIOScheduler()
logger = logging.getLogger(__name__)

# The manual email endpoint returns the last completed counters while the
# actual provider calls run as a BackgroundTask.  Keeping this small snapshot
# in process avoids blocking a request on Gmail/Graph OAuth and is safe to
# replace on every cycle.
LAST_EMAIL_SYNC_RESULT: dict[str, object] = {
    "gmail": None,
    "outlook": None,
    "total_inseridas": 0,
    "status": "never_run",
}


_NATIONAL_LOCATIONS = {"br", "brasil", "nacional", "todo brasil", "todo o brasil"}


def _preferencias_de_coleta() -> list[tuple[str, str]]:
    """Read current profile preferences on every cycle (there is no stale cache)."""

    db = SessionLocal()
    try:
        terms: list[tuple[str, str]] = []
        candidates = db.scalars(select(Candidate)).all()
        for candidate in candidates:
            try:
                preferences = json.loads(candidate.preferences_data or "{}")
            except (TypeError, ValueError):
                preferences = {}
            if not isinstance(preferences, dict):
                preferences = {}
            roles = preferences.get("target_roles") or candidate.target_roles or []
            locations = preferences.get("locations") or candidate.location or []
            if isinstance(roles, str):
                roles = [part.strip() for part in roles.replace(";", ",").split(",") if part.strip()]
            if isinstance(locations, str):
                locations = [part.strip() for part in locations.replace(";", ",").split(",") if part.strip()]
            roles = [str(item).strip() for item in roles if str(item).strip()]
            locations = [str(item).strip() for item in locations if str(item).strip()]
            terms.extend(
                (role, "" if location.casefold() in _NATIONAL_LOCATIONS else location)
                for role in roles[:8]
                for location in (locations[:8] or [""])
            )
        unique: list[tuple[str, str]] = []
        for term in terms:
            if tuple(part.casefold() for part in term) not in {
                tuple(part.casefold() for part in item) for item in unique
            }:
                unique.append(term)
        return unique[:24] or [(term, "") for term in TERMOS_MONITORADOS]
    finally:
        db.close()


def _termos_das_preferencias() -> list[str]:
    """Compatibility view used by diagnostics and older callers."""

    return [f"{term} {location}".strip() for term, location in _preferencias_de_coleta()]


async def executar_rotina_alertas() -> None:
    """Process pending matches and mark each notification as sent."""
    matches = await obter_matches_pendentes()
    if not matches:
        return
    for match in matches:
        titulo = match.get("vaga_titulo") or match.get("titulo") or "vaga"
        print(f"[Alerta] Enviando vaga para {match['candidato_nome']}: {titulo}")
        await registrar_alerta_enviado(match["candidato_id"], match["vaga_id"])


async def executar_rotina_varredura() -> None:
    """Collect monitored terms, upsert jobs and process their pending alerts."""
    print("[Scheduler] Iniciando coleta geral de vagas...")
    total = 0
    preferencias = _preferencias_de_coleta()
    print(
        "[Scheduler] Preferências lidas do banco neste ciclo: "
        + ", ".join(f"{term} {location}".strip() for term, location in preferencias)
    )
    for termo, localizacao in preferencias:
        try:
            vagas = await coletar_todas_as_fontes(termo, localizacao=localizacao, limite_por_fonte=30)
            total += await salvar_vagas_em_lote(vagas)
        except Exception as exc:  # noqa: BLE001 - one term must not stop the cycle
            print(f"[Scheduler] Erro no termo '{termo}' localidade='{localizacao}': {exc}")
    try:
        await executar_rotina_alertas()
    except Exception as exc:  # noqa: BLE001 - collection result remains useful
        print(f"[Scheduler] Erro ao processar alertas: {exc}")
    print(f"[Scheduler] Varredura concluída. Total salvas: {total}")


async def executar_rotina_limpeza() -> None:
    """Remove jobs without updates for 45 days."""
    removidas = await limpar_vagas_expiradas(dias_sem_atualizacao=45)
    print(f"[Housekeeping] {removidas} vagas antigas removidas.")


async def executar_rotina_sincronizacao_emails() -> dict[str, object]:
    """Synchronize every active Gmail and Outlook integration in one cycle."""

    print("[EmailSync] Iniciando sincronização de Gmail e Outlook...")
    resultados = await asyncio.gather(
        sync_all_gmail_integrations(),
        sync_all_outlook_integrations(),
        return_exceptions=True,
    )
    summary: dict[str, object] = {"gmail": None, "outlook": None, "total_inseridas": 0, "status": "completed"}
    for provider, result in zip(("Gmail", "Outlook"), resultados):
        if isinstance(result, Exception):
            print(f"[EmailSync] {provider} falhou: {type(result).__name__}: {result}")
            summary[provider.casefold()] = {"status": "erro", "erro": f"{type(result).__name__}: {result}"}
        else:
            print(f"[EmailSync] {provider}: {result}")
            key = provider.casefold()
            summary[key] = result
            if isinstance(result, dict):
                summary["total_inseridas"] = int(summary["total_inseridas"]) + int(
                    result.get("normalized", 0) or result.get("captured", 0) or 0
                )
    print("[EmailSync] Sincronização concluída.")
    LAST_EMAIL_SYNC_RESULT.clear()
    LAST_EMAIL_SYNC_RESULT.update(summary)
    return summary


def _housekeeping_sync() -> dict[str, int]:
    """Expire known OAuth tokens and retain only recent ingestion telemetry."""

    now = utc_now()
    cutoff = now - timedelta(days=15)
    db = SessionLocal()
    expired_tokens = 0
    purged_runs = 0
    try:
        integrations = db.scalars(
            select(EmailIntegration).where(
                EmailIntegration.token_expires_at.is_not(None),
                EmailIntegration.token_expires_at <= now,
                EmailIntegration.sync_status != "precisa_reconectar",
            )
        ).all()
        for integration in integrations:
            integration.sync_status = "precisa_reconectar"
            expired_tokens += 1

        # Runs are append-only diagnostics.  Delete by created/finished time,
        # preserving an in-progress run whose timestamps are still current.
        result = db.execute(
            delete(JobIngestionRun).where(
                or_(
                    JobIngestionRun.created_at < cutoff,
                    and_(
                        JobIngestionRun.finished_at.is_not(None),
                        JobIngestionRun.finished_at < cutoff,
                    ),
                )
            )
        )
        # The first predicate above intentionally uses the creation time as
        # the retention anchor.  Keep the count bounded and report it to logs.
        purged_runs = max(0, int(result.rowcount or 0))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[Housekeeping] falha ao expirar tokens ou purgar logs")
        raise
    finally:
        db.close()
    return {"tokens_expirados": expired_tokens, "logs_purgados": purged_runs}


async def executar_rotina_housekeeping() -> dict[str, int]:
    result = await asyncio.to_thread(_housekeeping_sync)
    print(
        f"[Housekeeping] tokens marcados para reconexão={result['tokens_expirados']} "
        f"logs de coleta purgados={result['logs_purgados']}"
    )
    return result


def iniciar_agendador() -> None:
    scheduler.add_job(
        executar_rotina_varredura,
        trigger=IntervalTrigger(hours=4),
        id="coleta_vagas",
        replace_existing=True,
    )
    scheduler.add_job(
        executar_rotina_limpeza,
        trigger=IntervalTrigger(hours=24),
        id="limpeza_vagas",
        replace_existing=True,
    )
    scheduler.add_job(
        executar_rotina_housekeeping,
        trigger=IntervalTrigger(hours=24),
        id="housekeeping_integracoes_logs",
        replace_existing=True,
    )
    scheduler.add_job(
        executar_rotina_sincronizacao_emails,
        trigger=IntervalTrigger(minutes=15),
        id="sincronizacao_emails",
        replace_existing=True,
    )
    scheduler.start()

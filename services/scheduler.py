"""Rotinas assíncronas de coleta, alertas e limpeza de vagas."""

import json

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import (
    SessionLocal,
    limpar_vagas_expiradas,
    obter_matches_pendentes,
    registrar_alerta_enviado,
    salvar_vagas_em_lote,
)
from app.models import Candidate
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


def _termos_das_preferencias() -> list[str]:
    """Build collection terms from every configured candidate profile."""

    db = SessionLocal()
    try:
        terms: list[str] = []
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
                f"{role} {location}" if location else role
                for role in roles[:8]
                for location in (locations[:8] or [""])
            )
        unique: list[str] = []
        for term in terms:
            if term.casefold() not in {item.casefold() for item in unique}:
                unique.append(term)
        return unique[:24] or list(TERMOS_MONITORADOS)
    finally:
        db.close()


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
    termos = _termos_das_preferencias()
    print(f"[Scheduler] Termos derivados das preferências: {', '.join(termos)}")
    for termo in termos:
        try:
            vagas = await coletar_todas_as_fontes(termo)
            total += await salvar_vagas_em_lote(vagas)
        except Exception as exc:  # noqa: BLE001 - one term must not stop the cycle
            print(f"[Scheduler] Erro no termo '{termo}': {exc}")
    try:
        await executar_rotina_alertas()
    except Exception as exc:  # noqa: BLE001 - collection result remains useful
        print(f"[Scheduler] Erro ao processar alertas: {exc}")
    print(f"[Scheduler] Varredura concluída. Total salvas: {total}")


async def executar_rotina_limpeza() -> None:
    """Remove jobs without updates for 45 days."""
    removidas = await limpar_vagas_expiradas(dias_sem_atualizacao=45)
    print(f"[Housekeeping] {removidas} vagas antigas removidas.")


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
    scheduler.start()

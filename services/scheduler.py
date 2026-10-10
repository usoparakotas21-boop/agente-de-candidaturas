"""Rotinas assíncronas de coleta, alertas e limpeza de vagas."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import (
    limpar_vagas_expiradas,
    obter_matches_pendentes,
    registrar_alerta_enviado,
    salvar_vagas_em_lote,
)
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
    for termo in TERMOS_MONITORADOS:
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

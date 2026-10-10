"""API de coleta e consulta do banco normalizado de vagas."""

from __future__ import annotations

import json
import hashlib
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from scrapers.job_collector import COLLECTORS, collect_report

from .auth import authenticated_user
from .database import consultar_vagas, salvar_vagas_em_lote
from .job_quality import assess_job_capture
from .models import Candidate, Job, QueueItem
from .queue_service import enqueue


router = APIRouter(prefix="/api/vagas", tags=["vagas"])
logger = logging.getLogger(__name__)


class CapturaVagasRequest(BaseModel):
    """Filtros opcionais; sem corpo a API usa as preferências salvas."""

    termos: list[str] = Field(default_factory=list, max_length=12)
    localizacoes: list[str] = Field(default_factory=list, max_length=12)
    modalidades: list[str] = Field(default_factory=list, max_length=8)
    fontes: list[str] = Field(default_factory=list, max_length=8)
    limite_por_fonte: int = Field(default=25, ge=1, le=100)
    usar_fallback_diagnostico: bool | None = None


def _owner_id(user: Any) -> str | None:
    if isinstance(user, dict):
        value = user.get("id") or user.get("uid") or user.get("sub")
    else:
        value = getattr(user, "id", None) or getattr(user, "uid", None)
    return str(value).strip() if value else None


def _split_values(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    result: list[str] = []
    for item in values:
        cleaned = str(item or "").strip()
        if cleaned and cleaned.casefold() not in {x.casefold() for x in result}:
            result.append(cleaned[:180])
    return result


def _preferences(db, user: Any) -> tuple[list[str], list[str], list[str]]:
    owner_id = _owner_id(user)
    query = select(Candidate).order_by(Candidate.id)
    if owner_id:
        query = query.where(Candidate.owner_id == owner_id)
    candidate = db.scalar(query)
    if candidate is None:
        return [], [], []
    try:
        data = json.loads(candidate.preferences_data or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    roles = _split_values(data.get("target_roles")) or _split_values(candidate.target_roles)
    locations = _split_values(data.get("locations")) or _split_values(candidate.location)
    modalities = [item.casefold() for item in _split_values(data.get("modalities"))]
    return roles, locations, modalities


def _queries(roles: list[str], locations: list[str]) -> list[str]:
    roles = roles[:8]
    locations = locations[:8]
    if roles and locations:
        return [f"{role} {location}" for role in roles for location in locations][:12]
    return (roles or locations or ["emprego"])[:12]


_NATIONAL_LOCATION_ALIASES = {
    "br",
    "brasil",
    "nacional",
    "todo brasil",
    "todo o brasil",
    "pais inteiro",
    "país inteiro",
    "qualquer lugar do brasil",
}


def _source_location(value: str) -> str:
    """Treat nationwide searches as no geographic restriction at the source."""

    normalized = " ".join(str(value or "").casefold().split())
    return "" if normalized in _NATIONAL_LOCATION_ALIASES else value


def _search_pairs(roles: list[str], locations: list[str]) -> list[tuple[str, str]]:
    """Keep role and location separate so each source gets its native filters."""

    if roles and locations:
        return [(role, _source_location(location)) for role in roles[:8] for location in locations[:8]][:12]
    if roles:
        return [(role, "") for role in roles[:12]]
    if locations:
        return [("emprego", _source_location(location)) for location in locations[:12]]
    return [("emprego", "")]


def _diagnostic_fallback_enabled(request: CapturaVagasRequest) -> bool:
    if request.usar_fallback_diagnostico is not None:
        return request.usar_fallback_diagnostico
    return os.getenv("JOB_CAPTURE_DIAGNOSTIC_FALLBACK", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _diagnostic_vagas(queries: list[str], modalities: list[str] | None = None) -> list[dict[str, Any]]:
    """Temporary, visibly marked records for testing the UI when sources are empty."""

    query = queries[0] if queries else "emprego"
    digest = hashlib.sha256(query.casefold().encode("utf-8")).hexdigest()[:16]
    modes = modalities or ["hibrido", "remoto", "presencial"]
    records = [
        {
            "id_externo": f"diagnostico-{digest}-1",
            "origem": "diagnostico",
            "titulo": f"[Diagnóstico] {query.title()} — oportunidade 1",
            "empresa": "Empresa exemplo (diagnóstico)",
            "localidade": "Bahia (exemplo)",
            "tipo_modalidade": modes[0 % len(modes)],
            "tipo_contrato": "CLT",
            "url_candidatura": f"https://example.com/candidatura/diagnostico/{digest}/1",
            "descricao": "Vaga simulada criada para validar a fila de decisão enquanto as fontes externas estão indisponíveis.",
            "tags": ["diagnostico", "teste"],
        },
        {
            "id_externo": f"diagnostico-{digest}-2",
            "origem": "diagnostico",
            "titulo": f"[Diagnóstico] {query.title()} — oportunidade 2",
            "empresa": "Organização exemplo (diagnóstico)",
            "localidade": "Salvador, BA (exemplo)",
            "tipo_modalidade": modes[1 % len(modes)],
            "tipo_contrato": "PJ",
            "url_candidatura": f"https://example.com/candidatura/diagnostico/{digest}/2",
            "descricao": "Vaga simulada criada para validar a fila de decisão enquanto as fontes externas estão indisponíveis.",
            "tags": ["diagnostico", "teste"],
        },
        {
            "id_externo": f"diagnostico-{digest}-3",
            "origem": "diagnostico",
            "titulo": f"[Diagnóstico] {query.title()} — oportunidade 3",
            "empresa": "Instituição exemplo (diagnóstico)",
            "localidade": "Feira de Santana, BA (exemplo)",
            "tipo_modalidade": modes[2 % len(modes)],
            "tipo_contrato": "CLT",
            "url_candidatura": f"https://example.com/candidatura/diagnostico/{digest}/3",
            "descricao": "Vaga simulada criada para validar a fila de decisão enquanto as fontes externas estão indisponíveis.",
            "tags": ["diagnostico", "teste"],
        },
    ]
    return records


def _captured_data(vaga: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    fields = quality.get("field_confidence") or {}
    health = quality.get("health") or {}
    salary_min = vaga.get("salario_minimo")
    salary_max = vaga.get("salario_maximo")
    salary = vaga.get("faixa_salarial") or ""
    if not salary and (salary_min is not None or salary_max is not None):
        salary = f"{salary_min or ''}–{salary_max or ''} {vaga.get('moeda') or 'BRL'}".strip()
    return {
        "title": vaga.get("titulo"),
        "company": vaga.get("empresa"),
        "location": vaga.get("localidade"),
        "modality": vaga.get("tipo_modalidade"),
        "contract_type": vaga.get("tipo_contrato") or "",
        "salary": salary,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "url": vaga.get("url_candidatura"),
        "description": vaga.get("descricao") or vaga.get("titulo") or "Vaga coletada de fonte pública.",
        "raw_excerpt": vaga.get("descricao") or vaga.get("titulo") or "",
        "confidence_title": fields.get("title"),
        "confidence_company": fields.get("company"),
        "confidence_description": fields.get("description"),
        "confidence_url": fields.get("url"),
        "confidence_overall": quality.get("confidence"),
        "modality_confidence": fields.get("modality"),
        "salary_confidence": fields.get("salary"),
        "contract_confidence": fields.get("contract_type"),
        "health_score": health.get("score"),
        "health_band": health.get("band"),
        "health_signals": health.get("signals", []),
        "fraud_suspected": health.get("fraud_suspected", False),
    }


@router.post("/capturar")
async def capturar_vagas(
    request: CapturaVagasRequest | None = None,
    user: Any = Depends(authenticated_user),
):
    """Dispara uma coleta manual usando cargos, locais e modalidades do perfil."""

    request = request or CapturaVagasRequest()
    from .database import SessionLocal

    db = SessionLocal()
    try:
        saved_roles, saved_locations, saved_modalities = _preferences(db, user)
    finally:
        db.close()

    roles = _split_values(request.termos) or saved_roles
    locations = _split_values(request.localizacoes) or saved_locations
    modalities = [item.casefold() for item in (_split_values(request.modalidades) or saved_modalities)]
    queries = _queries(roles, locations)
    search_pairs = _search_pairs(roles, locations)
    logger.info(
        "[Captura] inicio usuario=%s cargos=%s localizacoes=%s modalidades=%s consultas=%s pares=%s fontes=%s",
        _owner_id(user) or "local_user",
        roles,
        locations,
        modalities,
        queries,
        search_pairs,
        request.fontes or list(COLLECTORS),
    )
    collected: dict[str, Any] = {}
    source_errors: dict[str, str] = {}
    raw_total = 0
    filtered_total = 0
    for query, location in search_pairs:
        try:
            report = await collect_report(
                query,
                location=location,
                sources=request.fontes or None,
                limit_per_source=request.limite_por_fonte,
                concurrency=4,
            )
        except Exception as exc:  # noqa: BLE001 - report the source failure to the UI
            query_key = f"{query} {location}".strip()
            source_errors[query_key] = f"{type(exc).__name__}: {str(exc)[:220]}"
            logger.exception("[Captura] consulta=%r localizacao=%r falhou: %s", query, location, source_errors[query_key])
            continue
        source_errors.update(report.erros)
        raw_total += sum(report.brutos_por_fonte.values())
        logger.info(
            "[Captura] consulta=%r localizacao=%r brutos_por_fonte=%s resultados_unicos_do_relatorio=%d erros=%s",
            query,
            location,
            report.brutos_por_fonte,
            len(report.vagas),
            report.erros or "nenhum",
        )
        for vaga in report.vagas:
            item = vaga.model_dump(mode="json") if hasattr(vaga, "model_dump") else dict(vaga)
            if modalities and item.get("tipo_modalidade") not in modalities:
                continue
            filtered_total += 1
            collected.setdefault(str(item.get("chave_deduplicacao") or f"{item.get('origem')}:{item.get('id_externo')}"), item)

    vagas = list(collected.values())
    diagnostic_fallback = False
    if not vagas and _diagnostic_fallback_enabled(request):
        diagnostic_fallback = True
        vagas = _diagnostic_vagas(queries, modalities)
        logger.warning(
            "[Captura] fontes externas sem resultados (brutos=%d filtrados=%d erros=%d); "
            "injetando %d vagas de diagnóstico. Desative com JOB_CAPTURE_DIAGNOSTIC_FALLBACK=false.",
            raw_total,
            filtered_total,
            len(source_errors),
            len(vagas),
        )
    elif not vagas:
        logger.warning(
            "[Captura] nenhuma vaga retornada: brutos=%d filtrados=%d erros=%d fallback=desativado",
            raw_total,
            filtered_total,
            len(source_errors),
        )
    logger.info(
        "[Captura] fim consultas=%d brutos=%d apos_filtros=%d unicos=%d fallback_diagnostico=%s",
        len(queries),
        raw_total,
        filtered_total,
        len(vagas),
        diagnostic_fallback,
    )
    normalized = 0
    warnings: list[str] = []
    if vagas:
        try:
            normalized = await salvar_vagas_em_lote(vagas)
        except Exception as exc:  # noqa: BLE001 - queue remains usable as fallback
            logger.warning("Tabela normalizada indisponível durante captura manual: %s", exc)
            warnings.append("A tabela normalizada não foi atualizada; a fila local continua disponível.")

    queued = 0
    duplicates = 0
    queue_errors: list[str] = []
    owner_id = _owner_id(user) or "local_user"
    db = SessionLocal()
    try:
        for vaga in vagas:
            quality_input = {
                "title": vaga.get("titulo"),
                "company": vaga.get("empresa"),
                "location": vaga.get("localidade"),
                "modality": vaga.get("tipo_modalidade"),
                "contract_type": vaga.get("tipo_contrato") or "",
                "salary": _captured_data(vaga, {}).get("salary") or "",
                "url": vaga.get("url_candidatura"),
                "description": vaga.get("descricao") or vaga.get("titulo") or "Vaga coletada de fonte pública.",
            }
            try:
                quality = assess_job_capture(quality_input)
                item, created = enqueue(
                    db,
                    owner_id,
                    _captured_data(vaga, quality),
                    {
                        "decision": quality.get("decision", "REVISAR"),
                        "reasons": quality.get("reasons", []),
                        "engine_version": f"0.24.0/{quality.get('heuristics_version', 'capture')}",
                    },
                    source=str(vaga.get("origem") or "coleta")[:50],
                    source_ref=str(vaga.get("id_externo") or "")[:200],
                )
                queued += int(created)
                duplicates += int(not created)
            except Exception as exc:  # noqa: BLE001 - one bad source must not cancel all results
                db.rollback()
                queue_errors.append(str(exc)[:240])
    finally:
        db.close()

    return {
        "status": "COLETA_CONCLUIDA",
        "consultas": queries,
        "consultas_executadas": [{"termo": query, "localizacao": location} for query, location in search_pairs],
        "preferencias": {"cargos": roles, "localizacoes": locations, "modalidades": modalities},
        "capturadas": len(vagas),
        "total_encontradas": len(vagas),
        "normalizadas": normalized,
        "enfileiradas": queued,
        "novas_na_fila": queued,
        "duplicadas": duplicates,
        "fallback_diagnostico": diagnostic_fallback,
        "erros_fontes": source_errors,
        "fontes_com_erro": len(source_errors),
        "erros_fila": queue_errors,
        "avisos": warnings,
    }


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "source": row.get("origem"),
        "external_id": row.get("id_externo"),
        "title": row.get("titulo"),
        "company": row.get("empresa"),
        "location": row.get("localidade"),
        "modality": row.get("tipo_modalidade"),
        "contract_type": row.get("tipo_contrato"),
        "url": row.get("url_candidatura"),
        "published_at": row.get("data_publicacao"),
        "updated_at": row.get("updated_at"),
        "tags": row.get("tags") or [],
        "record_type": "catalog",
    }


@router.get("")
async def listar_vagas(
    termo: str | None = Query(default=None, max_length=180),
    modalidade: str | None = Query(default=None, max_length=80),
    origem: str | None = Query(default=None, max_length=80),
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: Any = Depends(authenticated_user),
):
    """Lista o banco normalizado com paginação e filtros do frontend."""

    try:
        rows = await consultar_vagas(termo, modalidade, limite, offset, origem=origem)
        total = int(rows[0].get("total_count") or 0) if rows else 0
        return {"items": [_serialize_row(row) for row in rows], "total": total, "limite": limite, "offset": offset, "source": "vagas"}
    except Exception as exc:  # noqa: BLE001 - legacy DB keeps the UI available
        logger.info("Consulta normalizada indisponível, usando fila/jobs legados: %s", exc)

    from .database import SessionLocal

    db = SessionLocal()
    try:
        owner_id = _owner_id(user)
        queue_query = select(QueueItem).order_by(QueueItem.captured_at.desc())
        if owner_id:
            queue_query = queue_query.where(QueueItem.owner_id == owner_id)
        if modalidade:
            queue_query = queue_query.where(QueueItem.modality == modalidade)
        if origem:
            queue_query = queue_query.where(QueueItem.source == origem)
        queue_rows = db.scalars(queue_query).all()
        result: list[dict[str, Any]] = []
        for item in queue_rows:
            if termo and termo.casefold() not in f"{item.title} {item.company} {item.location}".casefold():
                continue
            result.append({"id": item.id, "source": item.source, "external_id": item.source_ref, "title": item.title, "company": item.company, "location": item.location, "modality": item.modality, "contract_type": item.contract_type, "url": item.url, "record_type": "queue", "queue_status": item.status, "description": item.description})
        jobs_query = select(Job).order_by(Job.id.desc())
        if owner_id:
            jobs_query = jobs_query.where(Job.owner_id == owner_id)
        for job in db.scalars(jobs_query).all():
            if (origem and job.source != origem) or (modalidade and job.modality != modalidade):
                continue
            if termo and termo.casefold() not in f"{job.title} {job.company} {job.location}".casefold():
                continue
            result.append({"id": job.id, "source": job.source, "external_id": job.external_id, "title": job.title, "company": job.company, "location": job.location, "modality": job.modality, "contract_type": job.contract_type, "url": job.url, "record_type": "job", "description": job.description, "application_id": job.application.id if job.application else None, "application_status": job.application.status if job.application else None})
        total = len(result)
        return {"items": result[offset:offset + limite], "total": total, "limite": limite, "offset": offset, "source": "legacy"}
    finally:
        db.close()

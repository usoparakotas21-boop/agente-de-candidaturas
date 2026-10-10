"""API de coleta e consulta do banco normalizado de vagas."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from scrapers.job_collector import collect_report

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
    collected: dict[str, Any] = {}
    source_errors: dict[str, str] = {}
    for query in queries:
        try:
            report = await collect_report(
                query,
                sources=request.fontes or None,
                limit_per_source=request.limite_por_fonte,
                concurrency=4,
            )
        except Exception as exc:  # noqa: BLE001 - report the source failure to the UI
            source_errors[query] = f"{type(exc).__name__}: {str(exc)[:220]}"
            continue
        source_errors.update(report.erros)
        for vaga in report.vagas:
            item = vaga.model_dump(mode="json") if hasattr(vaga, "model_dump") else dict(vaga)
            if modalities and item.get("tipo_modalidade") not in modalities:
                continue
            collected.setdefault(str(item.get("chave_deduplicacao") or f"{item.get('origem')}:{item.get('id_externo')}"), item)

    vagas = list(collected.values())
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
        "preferencias": {"cargos": roles, "localizacoes": locations, "modalidades": modalities},
        "capturadas": len(vagas),
        "normalizadas": normalized,
        "enfileiradas": queued,
        "duplicadas": duplicates,
        "erros_fontes": source_errors,
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

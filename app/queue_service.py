"""
Servico de Fila - Camada unica de escrita em queue_items.
Gerencia o ciclo de vida dos itens na fila.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import QueueItem, Job
from app.decision_reasons import get_reason_label


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    session: Session,
    owner_id: str,
    captured: dict,
    decision_result: dict,
    source: str,
    source_ref: Optional[str] = None
) -> tuple[QueueItem, bool]:
    """
    Grava ou atualiza um item de fila.
    Retorna (item, criado: bool).
    Se decision_result.decision == "AUTOMATICA", promove no mesmo commit.
    """
    # O modo local nao possui usuario autenticado, mas queue_items.owner_id e
    # obrigatorio. Normalizar antes de consultar evita duplicatas locais.
    effective_owner_id = owner_id or "local_user"

    # Calcular dedup_hash
    dedup_hash = captured.get("dedup_hash")
    if not dedup_hash and captured.get("url"):
        # Simplificacao: hash da URL limpa
        import hashlib
        url_clean = captured["url"].split("?")[0].rstrip("/")
        dedup_hash = hashlib.sha256(url_clean.encode()).hexdigest()[:64]
    elif not dedup_hash:
        # Fallback: titulo + empresa
        import hashlib
        text = f"{captured.get('title', '')}|{captured.get('company', '')}|{captured.get('location', '')}"
        dedup_hash = hashlib.sha256(text.lower().encode()).hexdigest()[:64]

    # Verificar se ja existe
    existing = session.query(QueueItem).filter(
        and_(
            QueueItem.owner_id == effective_owner_id,
            QueueItem.dedup_hash == dedup_hash
        )
    ).first()

    if existing:
        # Atualizar contador
        existing.seen_count += 1
        existing.last_seen_at = utc_now()
        session.commit()
        return existing, False

    # Criar novo item
    item = QueueItem(
    health_score=captured.get("health_score"),
    health_band=captured.get("health_band"),
    health_signals=captured.get("health_signals", []),
    fraud_suspected=captured.get("fraud_suspected", False),

        owner_id=effective_owner_id,
        source=source,
        source_ref=source_ref,
        captured_at=utc_now(),
        title=captured.get("title"),
        company=captured.get("company"),
        location=captured.get("location"),
        modality=captured.get("modality"),
        url=captured.get("url"),
        description=captured.get("description"),
        raw_excerpt=captured.get("raw_excerpt"),
        confidence_title=captured.get("confidence_title"),
        confidence_company=captured.get("confidence_company"),
        confidence_description=captured.get("confidence_description"),
        confidence_url=captured.get("confidence_url"),
        confidence_overall=captured.get("confidence_overall"),
        decision=decision_result.get("decision", "REVISAR"),
        decision_reasons=decision_result.get("reasons", []),
        decision_engine_version=decision_result.get("engine_version", "0.23.0"),
        score=decision_result.get("score"),
        dedup_hash=dedup_hash,
        first_seen_at=utc_now(),
        last_seen_at=utc_now(),
    )

    session.add(item)
    session.flush()

    # Se for AUTOMATICA, promover imediatamente
    if item.decision == "AUTOMATICA":
        _promote_item(session, item, effective_owner_id)

    session.commit()
    return item, True


def _promote_item(session: Session, item: QueueItem, owner_id: Optional[str]) -> Job:
    """
    Promove um item da fila para job.
    Interno - usado por enqueue e approve.
    """
    # A aprovacao no modo local chega sem owner_id; o item e a fonte de
    # verdade para manter o job no mesmo escopo.
    effective_owner_id = owner_id or item.owner_id or "local_user"

    # Criar job
    import hashlib
    external_id = hashlib.sha256(
        f"{effective_owner_id}|{item.url or item.title}|{utc_now().isoformat()}".encode()
    ).hexdigest()[:16]

    job = Job(
        owner_id=effective_owner_id,
        source=item.source,
        external_id=external_id,
        company=item.company or "",
        title=item.title or "Vaga sem titulo",
        location=item.location or "",
        modality=item.modality or "",
        url=item.url or "",
        description=item.description or "",
    )
    session.add(job)
    session.flush()

    # Atualizar item
    item.status = "PROMOVIDO"
    item.job_id = job.id
    item.resolved_at = utc_now()
    item.resolved_by = "automatico"

    return job


def approve(session: Session, owner_id: Optional[str], item_id: int) -> dict:
    """
    PENDENTE -> PROMOVIDO.
    Cria o registro em jobs, dispara analise de aderencia.
    """
    query = session.query(QueueItem).filter(QueueItem.id == item_id)
    if owner_id is not None:
        query = query.filter(QueueItem.owner_id == owner_id)
    item = query.first()

    if not item:
        raise ValueError("Item nao encontrado")

    if item.status != "PENDENTE":
        return {
            "status": item.status,
            "job_id": item.job_id,
            "message": f"Item ja esta {item.status}"
        }

    # Promover
    job = _promote_item(session, item, owner_id)
    session.commit()

    return {
        "status": "PROMOVIDO",
        "job_id": job.id,
        "message": "Item promovido com sucesso"
    }


def reject(session: Session, owner_id: Optional[str], item_id: int, reason: Optional[str] = None) -> dict:
    """
    PENDENTE -> RECUSADO.
    Guarda o motivo informado pelo usuario.
    """
    query = session.query(QueueItem).filter(QueueItem.id == item_id)
    if owner_id is not None:
        query = query.filter(QueueItem.owner_id == owner_id)
    item = query.first()

    if not item:
        raise ValueError("Item nao encontrado")

    if item.status != "PENDENTE":
        return {
            "status": item.status,
            "message": f"Item ja esta {item.status}"
        }

    item.status = "RECUSADO"
    item.resolved_at = utc_now()
    item.resolved_by = "usuario"
    if reason:
        item.decision_reasons.append(f"RECUSADO_PELO_USUARIO: {reason}")

    session.commit()

    return {
        "status": "RECUSADO",
        "message": "Item recusado com sucesso"
    }


def expire_stale(session: Session, ttl_days: int = 14) -> int:
    """
    Rotina do worker.
    PENDENTE antigo -> EXPIRADO.
    Retorna quantidade de itens expirados.
    """
    from datetime import timedelta
    
    cutoff = utc_now() - timedelta(days=ttl_days)
    
    items = session.query(QueueItem).filter(
        and_(
            QueueItem.status == "PENDENTE",
            QueueItem.captured_at < cutoff
        )
    ).all()

    count = 0
    for item in items:
        item.status = "EXPIRADO"
        item.resolved_at = utc_now()
        item.resolved_by = "expiracao"
        count += 1

    session.commit()
    return count


def list_items(
    session: Session,
    owner_id: str,
    decision: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[QueueItem], int]:
    """
    Listagem paginada e filtrável.
    Retorna (items, total).
    """
    query = session.query(QueueItem)
    if owner_id is not None:
        query = query.filter(QueueItem.owner_id == owner_id)

    if decision:
        query = query.filter(QueueItem.decision == decision)
    
    if status:
        query = query.filter(QueueItem.status == status)

    total = query.count()
    items = query.order_by(QueueItem.captured_at.desc()).offset(offset).limit(limit).all()

    return items, total


def get_summary(session: Session, owner_id: str) -> dict:
    """
    Contagens por decisao e por status, para os cartoes do topo.
    """
    from sqlalchemy import func, case

    # Contagem por decisao
    decision_counts_query = session.query(
        QueueItem.decision,
        func.count(QueueItem.id).label("total"),
        func.sum(
            case(
                (QueueItem.captured_at >= utc_now().replace(hour=0, minute=0, second=0, microsecond=0), 1),
                else_=0
            )
        ).label("hoje")
    )
    if owner_id is not None:
        decision_counts_query = decision_counts_query.filter(QueueItem.owner_id == owner_id)
    decision_counts = decision_counts_query.group_by(QueueItem.decision).all()

    # Contagem por status para REVISAR
    revisar_query = session.query(func.count(QueueItem.id)).filter(
        QueueItem.decision == "REVISAR", QueueItem.status == "PENDENTE"
    )
    if owner_id is not None:
        revisar_query = revisar_query.filter(QueueItem.owner_id == owner_id)
    revisar_pendente = revisar_query.scalar() or 0

    descartar_query = session.query(func.count(QueueItem.id)).filter(
        QueueItem.decision == "DESCARTAR", QueueItem.status == "PENDENTE"
    )
    if owner_id is not None:
        descartar_query = descartar_query.filter(QueueItem.owner_id == owner_id)
    descartar_pendente = descartar_query.scalar() or 0

    expirado_query = session.query(func.count(QueueItem.id)).filter(
        QueueItem.status == "EXPIRADO"
    )
    if owner_id is not None:
        expirado_query = expirado_query.filter(QueueItem.owner_id == owner_id)
    expirado_total = expirado_query.scalar() or 0

    result = {
        "automatica": {"total": 0, "hoje": 0},
        "revisar": {"pendente": revisar_pendente, "total": 0},
        "descartar": {"pendente": descartar_pendente, "total": 0},
        "expirado": {"total": expirado_total},
    }

    for row in decision_counts:
        decision = row.decision
        if decision == "AUTOMATICA":
            result["automatica"]["total"] = row.total
            result["automatica"]["hoje"] = row.hoje or 0
        elif decision == "REVISAR":
            result["revisar"]["total"] = row.total
        elif decision == "DESCARTAR":
            result["descartar"]["total"] = row.total

    return result

